Saving/Resuming Study with RDB Backend &mdash; Optuna 4.9.0 documentation
 
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
 
- Saving/Resuming Study with RDB Backend

 
 

 
 
 
 

Note


Go to the end
to download the full example code.


# Saving/Resuming Study with RDB Backend


An RDB backend enables persistent experiments (i.e., to save and resume a study) as well as access to history of studies.
In addition, we can run multi-node optimization tasks with this feature, which is described in Easy Parallelization.


In this section, let’s try simple examples running on a local environment with SQLite DB.


Note


You can also utilize other RDB backends, e.g., PostgreSQL or MySQL, by setting the storage argument to the DB’s URL.
Please refer to SQLAlchemy’s document for how to set up the URL.


## New Study


We can create a persistent study by calling `create_study()` function as follows.
An SQLite file `example.db` is automatically initialized with a new study record.


import logging
import sys

import optuna

# Add stream handler of stdout to show the messages
optuna.logging.get_logger("optuna").addHandler(logging.StreamHandler(sys.stdout))
study_name = "example-study" # Unique identifier of the study.
storage_name = f"sqlite:///{study_name}.db"
study = optuna.create_study(study_name=study_name, storage=storage_name)


A new study created in RDB with name: example-study


To run a study, call `optimize()` method passing an objective function.


def objective(trial):
 x = trial.suggest_float("x", -10, 10)
 return (x - 2) ** 2


study.optimize(objective, n_trials=3)


Trial 0 finished with value: 64.32661512030677 and parameters: {'x': -6.020387466968586}. Best is trial 0 with value: 64.32661512030677.
Trial 1 finished with value: 64.11518039524498 and parameters: {'x': -6.007195538716723}. Best is trial 1 with value: 64.11518039524498.
Trial 2 finished with value: 21.514340201467718 and parameters: {'x': 6.638355333678923}. Best is trial 2 with value: 21.514340201467718.


## Resume Study


To resume a study, instantiate a `Study` object
passing the study name `example-study` and the DB URL `sqlite:///example-study.db`.


study = optuna.create_study(study_name=study_name, storage=storage_name, load_if_exists=True)
study.optimize(objective, n_trials=3)


Using an existing study with name 'example-study' instead of creating a new one.
Trial 3 finished with value: 25.34619834402948 and parameters: {'x': 7.034500803856275}. Best is trial 2 with value: 21.514340201467718.
Trial 4 finished with value: 8.976143672304394 and parameters: {'x': 4.9960213070511355}. Best is trial 4 with value: 8.976143672304394.
Trial 5 finished with value: 0.008875009922693617 and parameters: {'x': 2.0942072710712587}. Best is trial 5 with value: 0.008875009922693617.


Note that the storage doesn’t store the state of the instance of `samplers`
and `pruners`.
When we resume a study with a sampler whose `seed` argument is specified for
reproducibility, you need to restore the sampler with using `pickle` as follows:


import pickle

# Save the sampler with pickle to be loaded later.
with open("sampler.pkl", "wb") as fout:
 pickle.dump(study.sampler, fout)

restored_sampler = pickle.load(open("sampler.pkl", "rb"))
study = optuna.create_study(
 study_name=study_name, storage=storage_name, load_if_exists=True, sampler=restored_sampler
)
study.optimize(objective, n_trials=3)


## Experimental History


Note that this section requires the installation of Pandas:


$ pip install pandas


We can access histories of studies and trials via the `Study` class.
For example, we can get all trials of `example-study` as:


study = optuna.create_study(study_name=study_name, storage=storage_name, load_if_exists=True)
df = study.trials_dataframe(attrs=("number", "value", "params", "state"))


Using an existing study with name 'example-study' instead of creating a new one.


The method `trials_dataframe()` returns a pandas dataframe like:


print(df)


 number value params_x state
0 0 64.326615 -6.020387 COMPLETE
1 1 64.115180 -6.007196 COMPLETE
2 2 21.514340 6.638355 COMPLETE
3 3 25.346198 7.034501 COMPLETE
4 4 8.976144 4.996021 COMPLETE
5 5 0.008875 2.094207 COMPLETE


A `Study` object also provides properties
such as `trials`, `best_value`,
`best_params` (see also Lightweight, versatile, and platform agnostic architecture).


print("Best params: ", study.best_params)
print("Best value: ", study.best_value)
print("Best Trial: ", study.best_trial)
print("Trials: ", study.trials)


Best params: {'x': 2.0942072710712587}
Best value: 0.008875009922693617
Best Trial: FrozenTrial(number=5, state=<TrialState.COMPLETE: 1>, values=[0.008875009922693617], datetime_start=datetime.datetime(2026, 6, 1, 6, 28, 4, 14311), datetime_complete=datetime.datetime(2026, 6, 1, 6, 28, 4, 28060), params={'x': 2.0942072710712587}, user_attrs={}, system_attrs={}, intermediate_values={}, distributions={'x': FloatDistribution(high=10.0, log=False, low=-10.0, step=None)}, trial_id=6, value=None)
Trials: [FrozenTrial(number=0, state=<TrialState.COMPLETE: 1>, values=[64.32661512030677], datetime_start=datetime.datetime(2026, 6, 1, 6, 28, 3, 824527), datetime_complete=datetime.datetime(2026, 6, 1, 6, 28, 3, 853733), params={'x': -6.020387466968586}, user_attrs={}, system_attrs={}, intermediate_values={}, distributions={'x': FloatDistribution(high=10.0, log=False, low=-10.0, step=None)}, trial_id=1, value=None), FrozenTrial(number=1, state=<TrialState.COMPLETE: 1>, values=[64.11518039524498], datetime_start=datetime.datetime(2026, 6, 1, 6, 28, 3, 867993), datetime_complete=datetime.datetime(2026, 6, 1, 6, 28, 3, 882805), params={'x': -6.007195538716723}, user_attrs={}, system_attrs={}, intermediate_values={}, distributions={'x': FloatDistribution(high=10.0, log=False, low=-10.0, step=None)}, trial_id=2, value=None), FrozenTrial(number=2, state=<TrialState.COMPLETE: 1>, values=[21.514340201467718], datetime_start=datetime.datetime(2026, 6, 1, 6, 28, 3, 893760), datetime_complete=datetime.datetime(2026, 6, 1, 6, 28, 3, 907557), params={'x': 6.638355333678923}, user_attrs={}, system_attrs={}, intermediate_values={}, distributions={'x': FloatDistribution(high=10.0, log=False, low=-10.0, step=None)}, trial_id=3, value=None), FrozenTrial(number=3, state=<TrialState.COMPLETE: 1>, values=[25.34619834402948], datetime_start=datetime.datetime(2026, 6, 1, 6, 28, 3, 956741), datetime_complete=datetime.datetime(2026, 6, 1, 6, 28, 3, 977432), params={'x': 7.034500803856275}, user_attrs={}, system_attrs={}, intermediate_values={}, distributions={'x': FloatDistribution(high=10.0, log=False, low=-10.0, step=None)}, trial_id=4, value=None), FrozenTrial(number=4, state=<TrialState.COMPLETE: 1>, values=[8.976143672304394], datetime_start=datetime.datetime(2026, 6, 1, 6, 28, 3, 989368), datetime_complete=datetime.datetime(2026, 6, 1, 6, 28, 4, 3353), params={'x': 4.9960213070511355}, user_attrs={}, system_attrs={}, intermediate_values={}, distributions={'x': FloatDistribution(high=10.0, log=False, low=-10.0, step=None)}, trial_id=5, value=None), FrozenTrial(number=5, state=<TrialState.COMPLETE: 1>, values=[0.008875009922693617], datetime_start=datetime.datetime(2026, 6, 1, 6, 28, 4, 14311), datetime_complete=datetime.datetime(2026, 6, 1, 6, 28, 4, 28060), params={'x': 2.0942072710712587}, user_attrs={}, system_attrs={}, intermediate_values={}, distributions={'x': FloatDistribution(high=10.0, log=False, low=-10.0, step=None)}, trial_id=6, value=None)]


Total running time of the script: (0 minutes 0.840 seconds)


`Download Jupyter notebook: 001_rdb.ipynb`


`Download Python source code: 001_rdb.py`


`Download zipped: 001_rdb.zip`


Gallery generated by Sphinx-Gallery