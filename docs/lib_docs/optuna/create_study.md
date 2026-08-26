optuna.study.create_study &mdash; Optuna 4.9.0 documentation
 
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
 
- API Reference
 
- optuna.study
 
- optuna.study.create_study

 
 

 
 
 
 

# optuna.study.create_study


optuna.study.create_study(*, storage=None, sampler=None, pruner=None, study_name=None, direction=None, load_if_exists=False, directions=None)[source]

Create a new `Study`.


Example


import optuna


def objective(trial):
 x = trial.suggest_float("x", 0, 10)
 return x**2


study = optuna.create_study()
study.optimize(objective, n_trials=3)


Parameters:


- 
storage (str | storages.BaseStorage | None) – 
Database URL. If this argument is set to None,
`InMemoryStorage` is used, and the
`Study` will not be persistent.


Note


When a database URL is passed, Optuna internally uses SQLAlchemy to handle
the database. Please refer to SQLAlchemy’s document for further details.
If you want to specify non-default options to SQLAlchemy Engine, you can
instantiate `RDBStorage` with your desired options and
pass it to the `storage` argument instead of a URL.


- 
sampler ('samplers.BaseSampler' | None) – A sampler object that implements background algorithm for value suggestion.
If `None` is specified, `TPESampler` is used during
single-objective optimization and `NSGAIISampler` during
multi-objective optimization. See also `samplers`.


- 
pruner (pruners.BasePruner | None) – A pruner object that decides early stopping of unpromising trials. If `None`
is specified, `MedianPruner` is used as the default. See
also `pruners`.


- 
study_name (str | None) – Study’s name. If this argument is set to None, a unique name is generated
automatically.


- 
direction (str | StudyDirection | None) – 
Direction of optimization. Set `minimize` for minimization and `maximize` for
maximization. You can also pass the corresponding `StudyDirection`
object. `direction` and `directions` must not be specified at the same time.


Note


If none of direction and directions are specified, the direction of the study
is set to “minimize”.


- 
load_if_exists (bool) – Flag to control the behavior to handle a conflict of study names.
In the case where a study named `study_name` already exists in the `storage`,
a `DuplicatedStudyError` is raised if `load_if_exists` is
set to `False`.
Otherwise, the creation of the study is skipped, and the existing one is returned.


- 
directions (Sequence[str | StudyDirection] | None) – A sequence of directions during multi-objective optimization.
`direction` and `directions` must not be specified at the same time.


Returns:

A `Study` object.


Return type:

Study


See also


`optuna.create_study()` is an alias of `optuna.study.create_study()`.


See also


The Saving/Resuming Study with RDB Backend tutorial provides concrete examples to save and resume optimization using
RDB.