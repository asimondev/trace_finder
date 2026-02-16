# TRACE_FINDER - Finding Oracle Trace Files

**Version:** 0.93

**Author:** Andrej Simon, Oracle CSS Germany

**TRACE_FINDER** is a Python utility designed to search, filter, and download Oracle trace files and database alert logs across multiple nodes. It is particularly useful for consolidating diagnostic data before uploading it to Oracle Support.

## Features

- **Multi-Instance Support:** Easily handle RAC environments by defining multiple nodes.
- **Time-Based Filtering:** Use --since, --until, and --interval to find files within specific windows.
- **Pattern Matching:** Search for specific process traces (e.g., LGWR) using wildcards.
- **Automated Downloads:** Bulk download discovered traces to a local directory.

## Configuration

Before using **TRACE_FINDER**, you must prepare a JSON configuration file. This file tells the script where to find the diagnostic directories for each database, host(s) and instance(s).

### Configuration Attributes

| Attribute | Description |
| :--- | :--- |
| **db_unique_name** | The `DB_UNIQUE_NAME` of the Oracle database. |
| **instances** | A list of pairs: `["hostname", "instance_name"]`. This supports multiple nodes for RAC as well. |
| **diag_path** | The base Oracle diagnostic path. The directory `/diag/rdbms` must exist below this path. |

---

### Example: Single Instance Setup

If you have two separate databases on different hosts, your `test01.json` would look like this:

```json
[
  {
    "db_unique_name": "dba01_burg",
    "instances": [["bol8db1", "dba01"]],
    "diag_path": "/u01/oracle"
  },
  {
    "db_unique_name": "cdba1",
    "instances": [["bol8db2", "cdba1"]],
    "diag_path": "/u01/oracle"
  }
]
```

### Example: RAC Setup

For a Real Application Clusters (RAC) environment, define both nodes within the instances list:


```json
[
  {
    "db_unique_name": "dba",
    "instances": [
      ["bol8rac1a", "dba1"]
      ["bol8rac1b", "dba2"]
    ],
    "diag_path": "/u01/app/oracle"
  }
]

```
## Usage

```
./trace_finder.py -h
usage: trace_finder.py [-h] [-v] [-c CONFIG] [-d DIRECTORY] [-n NAME] [-l LAST_FILE] [-t TRACE_FILE] [--since SINCE]
                       [--until UNTIL] [-i INTERVAL] [-a] [--download] [--download_dir DOWNLOAD_DIR] [--local]
                       [--host HOST]

Oracle Trace Files Finder.

options:
  -h, --help            show this help message and exit
  -v, --version         show program's version number and exit
  -c CONFIG, --config CONFIG
                        config file path
  -d DIRECTORY, --directory DIRECTORY
                        default config directory path
  -n NAME, --name NAME  config file name
  -l LAST_FILE, --last_file LAST_FILE
                        latest trace file name
  -t TRACE_FILE, --trace_file TRACE_FILE
                        trace file name
  --since SINCE         only include files with mtime >= this local time (YYYY-MM-DD HH:MM:SS)
  --until UNTIL         only include files with mtime <= this local time (YYYY-MM-DD HH:MM:SS)
  -i INTERVAL, --interval INTERVAL
                        time window size: 10s, 5m, 2h, 1d (used with --since or --until)
  -a, --alert_log       print alert log path
  --download            download trace files
  --download_dir DOWNLOAD_DIR
                        download directory
  --local               run on local machine
  --host HOST           comma separated host names

=> Created by Andrej Simon, Oracle CSS Germany (https://github.com/asimondev/trace_finder)
```

The script uses the parameters DB_UNIQUE_NAME and instance name from the configuration file to build a path to the corresponding trace files. The script connects to remote hosts using SSH with the same user name.

You can specify the configuration file by:
- File name with *-c* / *--config* option
- Name only and the configuration directory using *-n*/*--name* and *-d* / *--directory* options
- Using file name and the environment variable TRACE_FINDER_CONFIG_DIR

## Examples

The following configuration file *~/tmp/test01.json* is used in the following examples:
```json
[
  {
    "db_unique_name": "dba01_burg",
    "instances": [["bol8db1", "dba01"]],
    "diag_path": "/u01/oracle"
  },
  {
    "db_unique_name": "cdba1",
    "instances": [["bol8db2", "cdba1"]],
    "diag_path": "/u01/oracle"
  }
]
```

### Locating and Downloading Alert Logs

You would like to see the path to the database alert log.
```
oracle@bol8db2> ./trace_finder.py -c ~/tmp/test01.json -a

Alert Log for DB_UNIQUE_NAME: dba01_burg
  - Host: bol8db1; ORACLE_SID:dba01
    => Alert Log: /u01/oracle/diag/rdbms/dba01_burg/dba01/trace/alert_dba01.log

Alert Log for DB_UNIQUE_NAME: cdba1
  - Host: bol8db2; ORACLE_SID:cdba1
    => Alert Log: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/alert_cdba1.log
oracle@bol8db2> 
```

You can use *--download* option to download these files to the *--download_dir* directory. The default is the current directory. 
```
mkdir ~/tmp/alerts

./trace_finder.py -c ~/tmp/test01.json -a --download --download_dir ~/tmp/alerts

Alert Log for DB_UNIQUE_NAME: dba01_burg
  - Host: bol8db1; ORACLE_SID:dba01
    => Alert Log: /u01/oracle/diag/rdbms/dba01_burg/dba01/trace/alert_dba01.log

Alert Log for DB_UNIQUE_NAME: cdba1
  - Host: bol8db2; ORACLE_SID:cdba1
    => Alert Log: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/alert_cdba1.log

ls -l ~/tmp/alerts/
total 356
-rw-r----- 1 oracle oinstall 198355  5. Nov  2024  alert_cdba1.log
-rw-r----- 1 oracle oinstall 163408  7. Mai  2025  alert_dba01.log
```

### Finding the Latest Trace File

Some Oracle background process writes trace files in the trace directory. You would like to get the latest file. For instance, I would like to get the latest trace files for the LGWR processes. You can use the option *-l* / *--last_file* <PATTERN> for this task.

```
./trace_finder.py -c ~/tmp/test01.json --last_file "*lgwr*trc" 

Finding last trace file for DB_UNIQUE_NAME: dba01_burg
  - Host: bol8db1; ORACLE_SID:dba01
    => File: /u01/oracle/diag/rdbms/dba01_burg/dba01/trace/dba01_lgwr_2018.trc
    => Timestamp: 2025-05-07 14:28:39

Finding last trace file for DB_UNIQUE_NAME: cdba1
  - Host: bol8db2; ORACLE_SID:cdba1
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_lgwr_19321.trc
    => Timestamp: 2024-11-05 19:24:34
```

The options *--download* and *--download_dir* works here as well.
```
ls -l ~/tmp/alerts
total 364
-rw-r----- 1 oracle oinstall 198355  5. Nov  2024  alert_cdba1.log
-rw-r----- 1 oracle oinstall 163408  7. Mai  2025  alert_dba01.log
-rw-r----- 1 oracle oinstall   1556  5. Nov  2024  cdba1_lgwr_19321.trc
-rw-r----- 1 oracle oinstall   1519  7. Mai  2025  dba01_lgwr_2018.trc
```

### Getting Trace Files

Use the option *-t* / *--trace_file* <PATTERN> to get the trace files.
```
./trace_finder.py -c ~/tmp/test01.json --trace_file "*ora*trc"
Finding traces for DB_UNIQUE_NAME: dba01_burg
  - Host: bol8db1; ORACLE_SID:dba01
    => File: /u01/oracle/diag/rdbms/dba01_burg/dba01/trace/dba01_ora_3691.trc
       Timestamp: 2025-05-07 14:28:49
    => File: /u01/oracle/diag/rdbms/dba01_burg/dba01/trace/dba01_ora_2935.trc
       Timestamp: 2025-05-07 14:26:52
...       
    => File: /u01/oracle/diag/rdbms/dba01_burg/dba01/trace/dba01_ora_8730.trc
       Timestamp: 2025-05-05 21:15:53

Finding traces for DB_UNIQUE_NAME: cdba1
  - Host: bol8db2; ORACLE_SID:cdba1
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_ora_16831.trc
       Timestamp: 2024-11-05 18:59:55
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_ora_16932.trc
       Timestamp: 2024-11-05 19:00:02
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_ora_16952.trc
       Timestamp: 2024-11-05 19:00:46
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_ora_16964.trc
       Timestamp: 2024-11-05 19:00:48
...
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_ora_19672.trc
       Timestamp: 2024-11-05 19:24:45

```

There are too many files. You could use the options *--local* and *--host* for local or only specific hosts. This way you don't have to edit your configuration file every time.

Often we need only the trace files for the specific time interval. The options *--since*, *--until* and *--interval* limits the output to the specified files.

```
oracle@bol8db2> ./trace_finder.py -c ~/tmp/test01.json --trace_file "*ora*trc" --local --since "2024-11-05 19:20:00" --until "2024-11-05 23:00:00"

Finding traces for DB_UNIQUE_NAME: dba01_burg
  - Host: bol8db1; ORACLE_SID:dba01

Finding traces for DB_UNIQUE_NAME: cdba1
  - Host: bol8db2; ORACLE_SID:cdba1
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_ora_18510.trc
       Timestamp: 2024-11-05 19:21:38
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_ora_19235.trc
       Timestamp: 2024-11-05 19:22:28
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_ora_19184.trc
       Timestamp: 2024-11-05 19:23:26
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_ora_19263.trc
       Timestamp: 2024-11-05 19:23:41
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_ora_19364.trc
       Timestamp: 2024-11-05 19:23:48
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_ora_19369.trc
       Timestamp: 2024-11-05 19:23:48
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_ora_19672.trc
       Timestamp: 2024-11-05 19:24:45
oracle@bol8db2> ./trace_finder.py -c ~/tmp/test01.json --trace_file "*ora*trc" --local --since "2024-11-05 19:20:00" --interval 3m                

Finding traces for DB_UNIQUE_NAME: dba01_burg
  - Host: bol8db1; ORACLE_SID:dba01

Finding traces for DB_UNIQUE_NAME: cdba1
  - Host: bol8db2; ORACLE_SID:cdba1
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_ora_18510.trc
       Timestamp: 2024-11-05 19:21:38
    => File: /u01/oracle/diag/rdbms/cdba1/cdba1/trace/cdba1_ora_19235.trc
       Timestamp: 2024-11-05 19:22:28
oracle@bol8db2> 
```


