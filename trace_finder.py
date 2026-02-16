#!/usr/bin/env python3

# Created by Andrej Simon, Oracle CSS Germany

import argparse
import os
import socket
import subprocess
from datetime import datetime
import json
import sys

from pathlib import Path

# Shell environment variable: TRACE_FINDER_CONFIG_DIR
config_directory = "/home/oracle/tmp"

# traces = [{
#     'db_unique_name': 'dba01_burg',
#     'instances': [
#         ['bol8db1','dba01']],
#     'diag_path' : '/u01/oracle'},
#     {'db_unique_name': 'cdba1',
#      'instances': [
#          ['bol8db2', 'cdba1']
#      ],
#      'diag_path': '/u01/oracle'}
# ]

def validate_traces(traces: object) -> None:
    if not isinstance(traces, list):
        raise TypeError("top-level JSON must be a list")

    for i, t in enumerate(traces):
        if not isinstance(t, dict):
            raise TypeError(f"traces[{i}] must be a dict")

        for key in ("db_unique_name", "instances", "diag_path"):
            if key not in t:
                raise KeyError(f"traces[{i}] missing '{key}'")

        if not isinstance(t["instances"], list):
            raise TypeError(f"traces[{i}]['instances'] must be a list")

def read_config_file(config_file):
    path = Path(config_file)

    if not path.exists():
        sys.exit(f"error: config file {path} not found")

    if not path.is_file():
        sys.exit(f"error: config file {path} is not a file")

    with path.open("r", encoding="utf-8") as f:
        ret = json.load(f)  # <- list of dicts, length can be anything

    validate_traces(ret)

    for trace in ret:
        trace['db_unique_name'] = trace['db_unique_name'].lower()

    return ret

def read_config_name(config_directory, config_name):
    path = Path(config_directory)
    if not path.is_dir():
        sys.exit(f"error: {config_directory} is not a directory")

    config_path = config_directory + "/" + config_name + ".json"
    return read_config_file(config_path)

def latest_matching_file(directory, pattern):
    directory = Path(directory)

    latest_path = None
    latest_mtime = None

    for p in directory.glob(pattern):
        if not p.is_file():
            continue
        mtime = p.stat().st_mtime
        if latest_mtime is None or mtime > latest_mtime:
            latest_path = p
            latest_mtime = mtime

    return latest_path, latest_mtime

def format_mtime(mtime_seconds):
    """
    Format mtime float into a readable local timestamp string.
    """
    return datetime.fromtimestamp(mtime_seconds).strftime("%Y-%m-%d %H:%M:%S")

def check_trace_dir(trace_dir):
    path = Path(trace_dir)
    if not path.exists():
        print(f"{trace_dir} does not exist")
        return False

    if not path.is_dir():
        print(f"{trace_dir} is not a directory")
        return False

    return True

def check_trace_file(trace_file, trace_dir=None):
    if trace_dir:
        if not check_trace_dir(trace_dir):
            return False
        trace_file = trace_dir + "/" + trace_file

    path = Path(trace_file)
    if not path.exists():
        print(f"{trace_file} does not exist")
        return False

    if not path.is_file():
        print(f"{trace_file} is not a file")
        return False

    return True

def make_trace_dir(db_unique_name, diag_path, sid):
    trace_dir = f"{diag_path}/diag/rdbms/{db_unique_name}/{sid}/trace"
    return trace_dir

def get_trace_dir(db_unique_name, diag_path, sid):
    trace_dir = make_trace_dir(db_unique_name, diag_path, sid)
    return trace_dir if check_trace_dir(trace_dir) else ""

def check_local_latest_file(db_unique_name, diag_path, host, sid, last_file):
    trace_dir = get_trace_dir(db_unique_name, diag_path, sid)
    if not trace_dir:
        return None

    if "*" not in last_file:
        last_file = f"*{last_file}*.trc"

    latest, mtime = latest_matching_file(trace_dir, last_file)
    if latest is None:
        print("error: no matching files found for {last_file}")
        return None

    return (latest, format_mtime(mtime))

def run_ssh(host, cmd):
    p = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", host, cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=True
    )
    if p.returncode != 0:
        raise RuntimeError(f"ssh {host} failed: {p.stderr.strip()}")
    return p.stdout.strip()

def check_remote_latest_file(db_unique_name, diag_path, host, sid, last_file):
    trace_dir = make_trace_dir(db_unique_name, diag_path, sid)

    if "*" not in last_file:
        last_file = f"*{last_file}*.trc"

    # Remote: find latest via ssh (ls -t) and stat mtime
    try:
        latest = run_ssh(
            host,
            f"cd {trace_dir} 2>/dev/null && ls -1t {last_file} 2>/dev/null | head -n 1")
    except Exception as e:
        print(f"{host}:{sid} => error checking remote trace dir: {e}")
        return None

    if not latest:
        print(f"error: {host}:{sid} => no matching files for {last_file}")
        return None

    remote_latest_path = f"{trace_dir}/{latest}"
    try:
        mtime = run_ssh(host, f"stat -c %Y {remote_latest_path}")
    except Exception as e:
        print(f"error: {host}:{sid} => found {remote_latest_path} but cannot stat: {e}")
        return None

    try:
        mtime_float = float(mtime)
    except ValueError:
        mtime_float = 0.0

    return remote_latest_path, format_mtime(mtime_float)

def find_last_trace(traces, last_file, is_local, host,
                    download, download_dir):
    short_host = socket.gethostname().split(".")[0]
    for trace in traces:
        print(f"\nFinding last trace file for DB_UNIQUE_NAME: {trace['db_unique_name']}")
        for host, sid in trace["instances"]:
            if not check_host_name(host, hosts):
                continue

            print(f"  - Host: {host}; ORACLE_SID:{sid}")
            if short_host == host:
                ret = check_local_latest_file(trace['db_unique_name'],
                              trace['diag_path'], host, sid, last_file)
                if ret:
                    print(f"    => File: {ret[0]}")
                    print(f"    => Timestamp: {ret[1]}")
                    if download and ret[0]:
                        copy_file(True, host, ret[0], download_dir)
                else:
                    print(f"    => File not found")

            else:
                if is_local:
                    continue
                else:
                    ret = check_remote_latest_file(trace['db_unique_name'],
                                    trace['diag_path'], host, sid, last_file)
                    if ret:
                        print(f"    => File: {ret[0]}")
                        print(f"    => Timestamp: {ret[1]}")
                        if download and ret[0]:
                            copy_file(False, host, ret[0], download_dir)
                    else:
                        print(f"    => File not found")

def check_remote_trace_files(db_unique_name, diag_path, host, sid, trace_file,
                             since_ts, until_ts):
    trace_dir = make_trace_dir(db_unique_name, diag_path, sid)
    file_name = f"{trace_dir}/{trace_file}"
    ret = []

    # Remote: find latest via ssh (ls -t) and stat mtime
    try:
        files = run_ssh(
            host,
            f"ls -1t {file_name}")
    except Exception as e:
        print(f"error: {host}:{sid} - error checking remote trace file {file_name}")
        return ret

    if not files:
        print(f"error: {host}:{sid} - no trace files found for {file_name}")
        return ret

    for f in files.splitlines():
        try:
            mtime = run_ssh(host, f"stat -c %Y {f}")
            try:
                mtime_float = float(mtime)
            except ValueError:
                mtime_float = None

            if since_ts is not None and until_ts is not None:
                if not in_time_window(mtime_float, since_ts, until_ts):
                    continue

            ret.append([f, mtime_float])
        except Exception as e:
            print(f"error: {host}:{sid} - found {f} but cannot stat: {e}")
            ret.append((f, None))

    for f in ret:
        try:
            mtime_float = float(f[1])
        except ValueError:
            mtime_float = 0.0

        f[1] = format_mtime(mtime_float) if f[1] else "N/A"

    return ret

def in_time_window(epoch_seconds, since_ts, until_ts):
    """
    Check if epoch_seconds is within [since_ts, until_ts] bounds (if provided).
    """
    if epoch_seconds is None:
        return False
    if since_ts is not None and epoch_seconds < since_ts:
        return False
    if until_ts is not None and epoch_seconds > until_ts:
        return False

    return True

def get_local_trace_files(directory, pattern, since_ts, until_ts):
    directory = Path(directory)

    ret = []

    for p in directory.glob(pattern):
        if not p.is_file():
            continue

        mtime = p.stat().st_mtime
        if since_ts is not None and until_ts is not None:
            if not in_time_window(mtime, since_ts, until_ts):
                continue

        ret.append([p.resolve(), format_mtime(mtime)])

    return ret

def check_local_trace_files(db_unique_name, diag_path, sid, trace_file,
                            since_ts, until_ts):
    trace_dir = get_trace_dir(db_unique_name, diag_path, sid)
    if not trace_dir:
        return []

    trace_files = get_local_trace_files(trace_dir, trace_file, since_ts, until_ts)
    if not trace_files:
        print(f"error: no matching files found for {trace_file}")

    return trace_files

def find_trace_files(traces, trace_file, is_local, hsot,
                     download, download_dir,
                     since_ts, until_ts):
    short_host = socket.gethostname().split(".")[0]
    for trace in traces:
        print(f"\nFinding traces for DB_UNIQUE_NAME: {trace['db_unique_name']}")
        for host, sid in trace["instances"]:
            if not check_host_name(host, hosts):
                continue

            print(f"  - Host: {host}; ORACLE_SID:{sid}")
            if short_host == host:
                trace_files = check_local_trace_files(trace['db_unique_name'],
                              trace['diag_path'], sid, trace_file,
                                                      since_ts, until_ts)
                if download and trace_files:
                    for f in trace_files:
                        copy_file(True, host, f[0], download_dir)

            else:
                if is_local:
                    continue
                else:
                    trace_files = check_remote_trace_files(trace['db_unique_name'],
                                    trace['diag_path'], host, sid, trace_file,
                                                           since_ts, until_ts)
                    if download and trace_files:
                        for f in trace_files:
                            copy_file(False, host, f[0], download_dir)

            if trace_files:
                for f in trace_files:
                    print(f"    => File: {f[0]}")
                    print(f"       Timestamp: {f[1]}")
            else:
                print(f"    => No files found")


def print_remote_alert_log(db_unique_name, diag_path, host, sid):
    trace_dir = make_trace_dir(db_unique_name, diag_path, sid)
    alert_log = f"{trace_dir}/alert_{sid}.log"

    try:
        file_name = run_ssh(
            host,
            f"ls -l {alert_log}")
    except Exception as e:
        print(f"error: {host} => error checking remote alert log {alert_log}")
        return None

    if not file_name:
        print(f"error: {host} => no matching alert log found")
        return None

    return alert_log

def print_local_alert_log(db_unique_name, diag_path, sid):
    trace_dir = get_trace_dir(db_unique_name, diag_path, sid)
    if trace_dir:
        trace_file = f"{trace_dir}/alert_{sid}.log"
        if check_trace_file(trace_file):
            return trace_file
        else:
            print(f"error: alert log {trace_file} not found")

    return None

def print_alert_log(traces, is_local, hosts, download, download_dir):
    short_host = socket.gethostname().split(".")[0]
    for trace in traces:
        print(f"\nAlert Log for DB_UNIQUE_NAME: {trace['db_unique_name']}")
        for host, sid in trace["instances"]:
            if not check_host_name(host, hosts):
                continue

            print(f"  - Host: {host}; ORACLE_SID:{sid}")
            if short_host == host:
                alert_log = print_local_alert_log(trace['db_unique_name'],
                              trace['diag_path'], sid)
                if download and alert_log:
                    copy_file(True, host, alert_log, download_dir)
            else:
                if is_local:
                    continue
                else:
                    alert_log = print_remote_alert_log(trace['db_unique_name'],
                                    trace['diag_path'], host, sid)
                    if download and alert_log:
                        copy_file(False, host, alert_log, download_dir)

            if alert_log:
                print(f"    => Alert Log: {alert_log}")
            else:
                print(f"    => Alert Log not found")

def copy_remote_file(host, source, target):
    p = subprocess.run(
        ["scp", "-q", "-p", "-o", "BatchMode=yes", f"{host}:{source}", target],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=True
    )
    if p.returncode != 0:
        print(f"error: scp from {host}:{source} to {target} failed: {p.stderr.strip()}")

def copy_local_file(source, target):
    p = subprocess.run(
        ["cp", "-a", source, target],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=True
    )
    if p.returncode != 0:
        print(f"error: cp from {source} to {target} failed: {p.stderr.strip()}")

def get_target_dir(local_dir):
    p = Path(local_dir or ".")
    if not p.is_dir():
        print(f"error: invalid download directory {p}")
        return None

    return p.resolve()

def copy_file(is_local, host, source, target):
    local_dir = get_target_dir(target)
    if not local_dir:
        return

    if is_local:
        copy_local_file(source, local_dir)
    else:
        copy_remote_file(host, source, local_dir)

def set_config_directory(default_dir, arg_dir):
    if arg_dir:
        return arg_dir

    env_dir = os.getenv("TRACE_FINDER_CONFIG_DIR")
    if env_dir:
        return env_dir

    return default_dir

def parse_time_arg(value):
    """
    Parse a local time string in format 'YYYY-MM-DD HH:MM:SS' into epoch seconds.
    Returns None if value is falsy.
    """
    if not value:
        return None

    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        print(f"error: invalid time format {value}; expected 'YYYY-MM-DD HH:MM:SS'")
        sys.exit(1)

    return dt.timestamp()

def parse_interval_arg(value):
    """
    Parse an interval like '10s', '5m', '2h', '1d' into seconds (int).
    Returns None if value is falsy.
    """
    if not value:
        return None

    s = str(value).strip().lower()
    if len(s) < 2:
        raise ValueError("invalid --interval, expected number + unit: 10s, 5m, 2h, 1d")

    unit = s[-1]
    number_part = s[:-1].strip()

    if unit not in ("s", "m", "h", "d"):
        raise ValueError("invalid --interval unit, use: s, m, h, d")

    try:
        amount = float(number_part)
    except ValueError:
        raise ValueError("invalid --interval number, expected e.g. 10s, 5m, 2h, 1d")

    if amount <= 0:
        raise ValueError("--interval must be > 0")

    multipliers = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 24 * 60 * 60,
    }
    return int(amount * multipliers[unit])

def check_time_parameters(since, until, interval):
    since_ts = parse_time_arg(since)
    until_ts = parse_time_arg(until)

    try:
        interval_sec = parse_interval_arg(interval)
    except (ValueError, TypeError) as e:
        print(f"error: {e}")
        sys.exit(1)

    if interval_sec:
        if since_ts:
            until_ts = since_ts + interval_sec
        elif until_ts:
            since_ts = until_ts - interval_sec
        else:
            print("error: either --since or --until must be set with --interval")
            sys.exit(1)
    else:
        # Both since and until must be set or unset.
        if (since_ts is None) != (until_ts is None):
            print("error: either --since or --until must be set")
            sys.exit(1)

    return since_ts, until_ts

def check_host_name(host, hosts):
    if not hosts:
        return True

    return host in hosts

def check_hosts(hosts):
    if not hosts:
        return []

    return hosts.split(",")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Oracle Trace Files Finder.",
                                     epilog=" => Created by Andrej Simon, Oracle CSS Germany (https://github.com/asimondev/trace_finder)")
    parser.add_argument("-v", "--version", action="version", version="%(prog)s 0.92")
    parser.add_argument("-c", "--config", help="config file path")
    parser.add_argument("-d", "--directory", help="default config directory path")
    parser.add_argument("-n", "--name", help="config file name")
    parser.add_argument("-l", "--last_file", help="latest trace file name")
    parser.add_argument("-t", "--trace_file", help="trace file name")
    parser.add_argument("--since",
                        help="only include files with mtime >= this local time (YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("--until",
                        help="only include files with mtime <= this local time (YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("-i", "--interval",
                        help="time window size: 10s, 5m, 2h, 1d (used with --since or --until)")
    parser.add_argument("-a", "--alert_log", action="store_true",
                        help="print alert log path")
    parser.add_argument("--download", action="store_true",
                        help="download trace files")
    parser.add_argument("--download_dir",
                        help="download directory")
    parser.add_argument("--local", action="store_true",
                        help="run on local machine")
    parser.add_argument("--host", help="comma separated host names")

    args = parser.parse_args()

    if args.local and args.host:
        parser.error("cannot use --local and --host together")
    hosts = check_hosts(args.host)

    if not args.name and not args.config:
        parser.error("either --name or --config must be provided")

    if args.since and args.until and args.interval:
        parser.error("cannot use --since, --until and --interval together")

    since_ts, until_ts = check_time_parameters(args.since, args.until, args.interval)
    if args.since and args.until and args.since > args.until:
        parser.error("since time must be before until time")

    if args.config:
        traces = read_config_file(args.config)
    else:
        config_dir = set_config_directory(config_directory, args.directory)
        traces = read_config_name(config_dir, args.name)

    if args.last_file:
        find_last_trace(traces, args.last_file, args.local, hosts,
                        args.download, args.download_dir)

    if args.trace_file:
        find_trace_files(traces, args.trace_file, args.local, hosts,
                         args.download, args.download_dir,
                         since_ts, until_ts)

    if args.alert_log:
        print_alert_log(traces, args.local, hosts,
                        args.download, args.download_dir)
