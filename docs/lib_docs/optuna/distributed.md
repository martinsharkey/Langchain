Easy Parallelization &mdash; Optuna 4.9.0 documentation
 
- 
 
- 
 
- 
 
- 
 
- 
 
- 
 
- 
 
- 
 
- 

 
 
- 
 
 
 
 
 
 
 
 
 
 
 
- 
 
- 


 
 
 
 
- 
 Key Features
 
 
- 
 Code Examples
 
 
- 
 Installation
 
 
- 
 Dashboard
 
 
- 
 OptunaHub
 
 
- 
 Blog
 
 
- 
 Videos
 
 
- 
 Paper
 
 
 
 
 

 
 

 

 
 
 
 
 
- 
 
- Easy Parallelization

 
 

 
 
 
 

Note


Go to the end
to download the full example code.


# Easy Parallelization


Optuna supports multiple ways to run parallel optimization.


- 
Multi-thread optimization:


- 
You can run multiple trials in parallel within a single process using the `n_jobs` parameter in `optimize()`.


- 
Multi-process optimization:


- 
You can run multiple processes sharing the same storage backend, such as RDB or a file.


- 
Multi-node optimization:


- 
You can run the same optimization study on multiple machines.


- 
If you need to perform optimization across thousands of processing nodes, you can use `GrpcStorageProxy` to run distributed optimization on multiple machines.


The following diagram shows which strategy is suitable for which use case.


## Multi-thread Optimization


Note


Recommended backends:

- 
`InMemoryStorage`


- 
`JournalStorage`


- 
`RDBStorage`


You can run multiple trials in parallel just by setting the `n_jobs`
parameter in `optimize()`.


Multi-thread optimization has traditionally been inefficient in Python due to the Global Interpreter Lock (GIL).
However, starting from Python 3.14 (pending official release), the GIL is expected to be removed.
This change will make multi-threading a good option, especially for parallel optimization.


import optuna
from optuna.storages import JournalStorage
from optuna.storages.journal import JournalFileBackend
from optuna.trial import Trial
import threading


def objective(trial: Trial):
 print(f"Running trial {trial.number=} in {threading.current_thread().name}")
 x = trial.suggest_float("x", -10, 10)
 return (x - 2) ** 2


study = optuna.create_study(
 storage=JournalStorage(JournalFileBackend(file_path="./journal.log")),
)
study.optimize(objective, n_trials=20, n_jobs=4)


Running trial trial.number=0 in ThreadPoolExecutor-1_0
Running trial trial.number=1 in ThreadPoolExecutor-1_1
Running trial trial.number=2 in ThreadPoolExecutor-1_3
Running trial trial.number=3 in ThreadPoolExecutor-1_2
Running trial trial.number=4 in ThreadPoolExecutor-1_1
Running trial trial.number=5 in ThreadPoolExecutor-1_3
Running trial trial.number=6 in ThreadPoolExecutor-1_2
Running trial trial.number=7 in ThreadPoolExecutor-1_0
Running trial trial.number=8 in ThreadPoolExecutor-1_1
Running trial trial.number=9 in ThreadPoolExecutor-1_3
Running trial trial.number=10 in ThreadPoolExecutor-1_2
Running trial trial.number=11 in ThreadPoolExecutor-1_0
Running trial trial.number=12 in ThreadPoolExecutor-1_1
Running trial trial.number=13 in ThreadPoolExecutor-1_3
Running trial trial.number=14 in ThreadPoolExecutor-1_2
Running trial trial.number=15 in ThreadPoolExecutor-1_0
Running trial trial.number=16 in ThreadPoolExecutor-1_1
Running trial trial.number=17 in ThreadPoolExecutor-1_3
Running trial trial.number=18 in ThreadPoolExecutor-1_0
Running trial trial.number=19 in ThreadPoolExecutor-1_2


## Multi-process Optimization with JournalStorage


Note


Recommended backends:

- 
`JournalStorage`


- 
`RDBStorage`


You can run multiple processes for optimization by using shared storage.
Since `InMemoryStorage` is not designed to be shared across processes,
it cannot be used for multi-process optimization.


The following example shows how to use `JournalStorage`
for multi-process optimization with `multiprocessing` module.


import optuna
from multiprocessing import Pool
from optuna.storages import JournalStorage
from optuna.storages.journal import JournalFileBackend
import os


def objective(trial):
 print(f"Running trial {trial.number=} in process {os.getpid()}")
 x = trial.suggest_float("x", -10, 10)
 return (x - 2) ** 2


def run_optimization(_):
 study = optuna.create_study(
 study_name="journal_storage_multiprocess",
 storage=JournalStorage(JournalFileBackend(file_path="./journal.log")),
 load_if_exists=True, # Useful for multi-process or multi-node optimization.
 )
 study.optimize(objective, n_trials=3)

if __name__ == "__main__":
 with Pool(processes=4) as pool:
 pool.map(run_optimization, range(12))


Out:


$ python3 multiprocess_example.py
Running trial trial.number=1 in process 4605
Running trial trial.number=2 in process 4604
Running trial trial.number=3 in process 4607
Running trial trial.number=4 in process 4606
Running trial trial.number=5 in process 4605
Running trial trial.number=6 in process 4607
Running trial trial.number=7 in process 4604
Running trial trial.number=8 in process 4605
...


## Multi-node Optimization with RDBStorage


Since `JournalFileBackend` uses file locks on the local filesystem, it operates safely for multiple processes on the same host. However, if accessed simultaneously from multiple machines via NFS (or similar), the file locks may not work correctly, which could lead to race conditions.
it is likely to cause race conditions when accessed by multiple machines.


Therefore, for multi-node optimization, it is recommended to use `RDBStorage`.
You can use MySQL, PostgreSQL, or other RDB backends.


For example, when using MySQL, you need to set up a MySQL server and create a database for Optuna.


$ mysql -u username -e "CREATE DATABASE IF NOT EXISTS example"


Then, you can use this MySQL database as a storage backend by setting the
MySQL URL as the value of the `storage` parameter in `create_study()`.


import optuna


def objective(trial):
 x = trial.suggest_float("x", -10, 10)
 return (x - 2) ** 2


if __name__ == "__main__":
 study = optuna.create_study(
 study_name="distributed_test",
 storage="mysql://username:password@127.0.0.1:3306/example",
 load_if_exists=True,
 )
 study.optimize(objective, n_trials=100)


You can run this example on multiple machines


Machine 1:


$ python3 distributed_example.py
[I 2025-06-03 14:07:45,306] A new study created in RDB with name: distributed_test
[I 2025-06-03 14:08:45,450] Trial 0 finished with value: 12.694308312865278 and parameters: {'x': -1.5629072837873959}. Best is trial 0 with value: 12.694308312865278.
[I 2025-06-03 14:09:45,482] Trial 2 finished with value: 121.80632032697125 and parameters: {'x': -9.036590067904635}. Best is trial 0 with value: 12.694308312865278.


Machine 2:


$ python3 distributed_example.py
[I 2025-06-03 14:07:49,318] Using an existing study with name 'distributed_test' instead of creating a new one.
[I 2025-06-03 14:08:49,442] Trial 1 finished with value: 0.21258674253407828 and parameters: {'x': 1.5389287012466746}. Best is trial 31 with value: 9.19159178106083e-05.
[I 2025-06-03 14:09:49,480] Trial 3 finished with value: 0.24343413718999274 and parameters: {'x': 2.493390451052706}. Best is trial 31 with value: 9.19159178106083e-05.


## Multi-node Optimization with GrpcStorageProxy


However, if you are running thousands of process nodes, an RDB server may not be able to handle the load.
In that case, you can use `GrpcStorageProxy`
to distribute the server load.


`GrpcStorageProxy` is a proxy storage layer that internally uses `RDBStorage` as its backend.
It can efficiently handle high-throughput concurrent requests from multiple machines.


The following example shows how to use `GrpcStorageProxy`.
Since `GrpcStorageProxy` is a proxy storage,
you need to run a gRPC server with `RDBStorage` backend first.


from optuna.storages import run_grpc_proxy_server
from optuna.storages import get_storage

storage = get_storage("mysql+pymysql://username:password@127.0.0.1:3306/example")
run_grpc_proxy_server(storage, host="localhost", port=13000)


Out:


$ python3 grpc_proxy_server.py
[I 2025-06-03 13:57:38,328] Server started at localhost:13000
[I 2025-06-03 13:57:38,328] Listening...


Then, on each machine, you can run the following code to connect to the gRPC proxy storage.


import optuna

from optuna.storages import GrpcStorageProxy


def objective(trial):
 x = trial.suggest_float("x", -10, 10)
 return (x - 2) ** 2


if __name__ == "__main__":
 storage = GrpcStorageProxy(host="localhost", port=13000)
 study = optuna.create_study(
 study_name="grpc_proxy_multinode",
 storage=storage,
 load_if_exists=True,
 )
 study.optimize(objective, n_trials=50)


Total running time of the script: (0 minutes 0.109 seconds)


`Download Jupyter notebook: 004_distributed.ipynb`


`Download Python source code: 004_distributed.py`


`Download zipped: 004_distributed.zip`


Gallery generated by Sphinx-Gallery