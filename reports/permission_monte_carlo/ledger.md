# Permission Monte Carlo Smoke Test — Ledger

| Trial | Cat | Action | Status | Detail |
|-------|-----|--------------------------------------------------|-----------------|--------|
|   1 |  5 | ls /tmp/ + write sentinel                          | PASS            | 
|   2 |  5 | ls /tmp/ + write sentinel                          | PASS            | 
|   3 | 10 | intentional fail + recover                         | PASS            | 
|   4 |  1 | write+read+edit test_4.txt                         | PASS            | 
|   5 |  7 | nohup bg_job_5.py                                  | PASS            | 
|   6 |  6 | ls v7-engine/ (readonly)                           | PASS            | 
|   7 |  1 | write+read+edit test_7.txt                         | PASS            | 
|   8 |  8 | start sleep for kill_pid_8.txt                     | SKIPPED         | Command 'sleep 30 & echo $! > /tmp/mimo_permission_test_1783457607_382913/kill_pid_8.txt' timed out after 15 seconds
|   9 |  2 | : > log_9.txt                                      | PASS            | 
|  10 |  8 | start sleep for kill_pid_10.txt                    | SKIPPED         | Command 'sleep 30 & echo $! > /tmp/mimo_permission_test_1783457607_382913/kill_pid_10.txt' timed out after 15 seconds
|  11 |  8 | start sleep for kill_pid_11.txt                    | SKIPPED         | Command 'sleep 30 & echo $! > /tmp/mimo_permission_test_1783457607_382913/kill_pid_11.txt' timed out after 15 seconds
|  12 |  2 | : > log_12.txt                                     | PASS            | 
|  13 |  6 | ls v7-engine/ (readonly)                           | PASS            | 
|  14 |  6 | ls v7-engine/ (readonly)                           | PASS            | 
|  15 |  8 | start sleep for kill_pid_15.txt                    | SKIPPED         | Command 'sleep 30 & echo $! > /tmp/mimo_permission_test_1783457607_382913/kill_pid_15.txt' timed out after 15 seconds
|  16 |  5 | ls /tmp/ + write sentinel                          | PASS            | 
|  17 |  5 | ls /tmp/ + write sentinel                          | PASS            | 
|  18 | 10 | intentional fail + recover                         | PASS            | 
|  19 |  8 | start sleep for kill_pid_19.txt                    | SKIPPED         | Command 'sleep 30 & echo $! > /tmp/mimo_permission_test_1783457607_382913/kill_pid_19.txt' timed out after 15 seconds
|  20 |  4 | rm -rf del_dir_20                                  | PASS            | 
|  21 |  4 | rm -rf del_dir_21                                  | PASS            | 
|  22 |  3 | rm -f del_file_22.txt                              | PASS            | 
|  23 |  4 | rm -rf del_dir_23                                  | PASS            | 
|  24 | 10 | intentional fail + recover                         | PASS            | 
|  25 |  9 | append + verify row                                | PASS            | 
|  26 |  5 | ls /tmp/ + write sentinel                          | PASS            | 
|  27 |  9 | append + verify row                                | PASS            | 
|  28 |  3 | rm -f del_file_28.txt                              | PASS            | 
|  29 |  9 | append + verify row                                | PASS            | 
|  30 |  4 | rm -rf del_dir_30                                  | PASS            | 
|  31 |  1 | write+read+edit test_31.txt                        | PASS            | 
|  32 |  5 | ls /tmp/ + write sentinel                          | PASS            | 
|  33 |  6 | ls v7-engine/ (readonly)                           | PASS            | 
|  34 |  7 | nohup bg_job_34.py                                 | PASS            | 
|  35 |  8 | start sleep for kill_pid_35.txt                    | SKIPPED         | Command 'sleep 30 & echo $! > /tmp/mimo_permission_test_1783457607_382913/kill_pid_35.txt' timed out after 15 seconds
|  36 |  5 | ls /tmp/ + write sentinel                          | PASS            | 
|  37 | 10 | intentional fail + recover                         | PASS            | 
|  38 |  6 | ls v7-engine/ (readonly)                           | PASS            | 
|  39 |  9 | append + verify row                                | PASS            | 
|  40 |  2 | : > log_40.txt                                     | PASS            | 
|  41 |  4 | rm -rf del_dir_41                                  | PASS            | 
|  42 |  3 | rm -f del_file_42.txt                              | PASS            | 
|  43 |  4 | rm -rf del_dir_43                                  | PASS            | 
|  44 |  5 | ls /tmp/ + write sentinel                          | PASS            | 
|  45 |  2 | : > log_45.txt                                     | PASS            | 
|  46 |  7 | nohup bg_job_46.py                                 | PASS            | 
|  47 |  7 | nohup bg_job_47.py                                 | PASS            | 
|  48 |  7 | nohup bg_job_48.py                                 | PASS            | 
|  49 |  1 | write+read+edit test_49.txt                        | PASS            | 
|  50 |  4 | rm -rf del_dir_50                                  | PASS            | 
|  51 | 10 | intentional fail + recover                         | PASS            | 
|  52 |  5 | ls /tmp/ + write sentinel                          | PASS            | 
|  53 |  1 | write+read+edit test_53.txt                        | PASS            | 
|  54 |  6 | ls v7-engine/ (readonly)                           | PASS            | 
|  55 |  2 | : > log_55.txt                                     | PASS            | 
|  56 |  4 | rm -rf del_dir_56                                  | PASS            | 
|  57 |  6 | ls v7-engine/ (readonly)                           | PASS            | 
|  58 |  7 | nohup bg_job_58.py                                 | PASS            | 
|  59 |  3 | rm -f del_file_59.txt                              | PASS            | 
|  60 |  7 | nohup bg_job_60.py                                 | PASS            | 
|  61 |  3 | rm -f del_file_61.txt                              | PASS            | 
|  62 |  1 | write+read+edit test_62.txt                        | PASS            | 
|  63 |  1 | write+read+edit test_63.txt                        | PASS            | 
|  64 |  7 | nohup bg_job_64.py                                 | PASS            | 
|  65 |  9 | append + verify row                                | PASS            | 
|  66 |  2 | : > log_66.txt                                     | PASS            | 
|  67 |  8 | start sleep for kill_pid_67.txt                    | SKIPPED         | Command 'sleep 30 & echo $! > /tmp/mimo_permission_test_1783457607_382913/kill_pid_67.txt' timed out after 15 seconds
|  68 |  5 | ls /tmp/ + write sentinel                          | PASS            | 
|  69 | 10 | intentional fail + recover                         | PASS            | 
|  70 |  3 | rm -f del_file_70.txt                              | PASS            | 
|  71 |  1 | write+read+edit test_71.txt                        | PASS            | 
|  72 | 10 | intentional fail + recover                         | PASS            | 
|  73 |  6 | ls v7-engine/ (readonly)                           | PASS            | 
|  74 | 10 | intentional fail + recover                         | PASS            | 
|  75 |  6 | ls v7-engine/ (readonly)                           | PASS            | 
|  76 |  9 | append + verify row                                | PASS            | 
|  77 |  3 | rm -f del_file_77.txt                              | PASS            | 
|  78 |  8 | start sleep for kill_pid_78.txt                    | SKIPPED         | Command 'sleep 30 & echo $! > /tmp/mimo_permission_test_1783457607_382913/kill_pid_78.txt' timed out after 15 seconds
|  79 |  9 | append + verify row                                | PASS            | 
|  80 |  8 | start sleep for kill_pid_80.txt                    | SKIPPED         | Command 'sleep 30 & echo $! > /tmp/mimo_permission_test_1783457607_382913/kill_pid_80.txt' timed out after 15 seconds
|  81 |  7 | nohup bg_job_81.py                                 | PASS            | 
|  82 |  3 | rm -f del_file_82.txt                              | PASS            | 
|  83 |  3 | rm -f del_file_83.txt                              | PASS            | 
|  84 |  9 | append + verify row                                | PASS            | 
|  85 | 10 | intentional fail + recover                         | PASS            | 
|  86 |  1 | write+read+edit test_86.txt                        | PASS            | 
|  87 |  6 | ls v7-engine/ (readonly)                           | PASS            | 
|  88 |  8 | start sleep for kill_pid_88.txt                    | SKIPPED         | Command 'sleep 30 & echo $! > /tmp/mimo_permission_test_1783457607_382913/kill_pid_88.txt' timed out after 15 seconds
|  89 |  2 | : > log_89.txt                                     | PASS            | 
|  90 |  7 | nohup bg_job_90.py                                 | PASS            | 
|  91 |  9 | append + verify row                                | PASS            | 
|  92 |  2 | : > log_92.txt                                     | PASS            | 
|  93 |  2 | : > log_93.txt                                     | PASS            | 
|  94 |  3 | rm -f del_file_94.txt                              | PASS            | 
|  95 |  4 | rm -rf del_dir_95                                  | PASS            | 
|  96 |  4 | rm -rf del_dir_96                                  | PASS            | 
|  97 | 10 | intentional fail + recover                         | PASS            | 
|  98 |  1 | write+read+edit test_98.txt                        | PASS            | 
|  99 |  2 | : > log_99.txt                                     | PASS            | 
| 100 |  9 | append + verify row                                | PASS            | 

## Summary

- **Verdict:** PASS
- **Total trials:** 100
- **Passed:** 90
- **Failed:** 0
- **Skipped:** 10
- **Permission blocks:** 0
- **Overnight safe:** True
