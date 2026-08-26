Lightweight, versatile, and platform agnostic architecture &mdash; Optuna 4.9.0 documentation
 
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
 
- Lightweight, versatile, and platform agnostic architecture

 
 

 
 
 
 

Note


Go to the end
to download the full example code.


# Lightweight, versatile, and platform agnostic architecture


Optuna is entirely written in Python and has few dependencies.
This means that we can quickly move to the real example once you get interested in Optuna.


## Quadratic Function Example


Usually, Optuna is used to optimize hyperparameters, but as an example,
let’s optimize a simple quadratic function: \((x - 2)^2\).


First of all, import `optuna`.


import optuna


In optuna, conventionally functions to be optimized are named objective.


def objective(trial):
 x = trial.suggest_float("x", -10, 10)
 return (x - 2) ** 2


This function returns the value of \((x - 2)^2\). Our goal is to find the value of `x`
that minimizes the output of the `objective` function. This is the “optimization.”
During the optimization, Optuna repeatedly calls and evaluates the objective function with
different values of `x`.


A `Trial` object corresponds to a single execution of the objective
function and is internally instantiated upon each invocation of the function.


The suggest APIs (for example, `suggest_float()`) are called
inside the objective function to obtain parameters for a trial.
`suggest_float()` selects parameters uniformly within the range
provided. In our example, from \(-10\) to \(10\).


To start the optimization, we create a study object and pass the objective function to method
`optimize()` as follows.


study = optuna.create_study()
study.optimize(objective, n_trials=100)


You can get the best parameter as follows.


best_params = study.best_params
found_x = best_params["x"]
print(f"Found x: {found_x}, (x - 2)^2: {(found_x - 2) ** 2}")


Found x: 1.9795173001678286, (x - 2)^2: 0.0004195409924148358


We can see that the `x` value found by Optuna is close to the optimal value of `2`.


Note


When used to search for hyperparameters in machine learning,
usually the objective function would return the loss or accuracy
of the model.


## Study Object


Let us clarify the terminology in Optuna as follows:


- 
Trial: A single call of the objective function


- 
Study: An optimization session, which is a set of trials


- 
Parameter: A variable whose value is to be optimized, such as `x` in the above example


In Optuna, we use the study object to manage optimization.
Method `create_study()` returns a study object.
A study object has useful properties for analyzing the optimization outcome.


To get the dictionary of parameter name and parameter values:


study.best_params


{'x': 1.9795173001678286}


To get the best observed value of the objective function:


study.best_value


0.0004195409924148358


To get the best trial:


study.best_trial


FrozenTrial(number=96, state=<TrialState.COMPLETE: 1>, values=[0.0004195409924148358], datetime_start=datetime.datetime(2026, 6, 1, 6, 25, 45, 868836), datetime_complete=datetime.datetime(2026, 6, 1, 6, 25, 45, 870308), params={'x': 1.9795173001678286}, user_attrs={}, system_attrs={}, intermediate_values={}, distributions={'x': FloatDistribution(high=10.0, log=False, low=-10.0, step=None)}, trial_id=96, value=None)


To get all trials:


study.trials
for trial in study.trials[:2]: # Show first two trials
 print(trial)


FrozenTrial(number=0, state=<TrialState.COMPLETE: 1>, values=[40.26765860870116], datetime_start=datetime.datetime(2026, 6, 1, 6, 25, 45, 729814), datetime_complete=datetime.datetime(2026, 6, 1, 6, 25, 45, 730531), params={'x': -4.345680310943907}, user_attrs={}, system_attrs={}, intermediate_values={}, distributions={'x': FloatDistribution(high=10.0, log=False, low=-10.0, step=None)}, trial_id=0, value=None)
FrozenTrial(number=1, state=<TrialState.COMPLETE: 1>, values=[23.21839915307801], datetime_start=datetime.datetime(2026, 6, 1, 6, 25, 45, 730761), datetime_complete=datetime.datetime(2026, 6, 1, 6, 25, 45, 730998), params={'x': 6.818547411106174}, user_attrs={}, system_attrs={}, intermediate_values={}, distributions={'x': FloatDistribution(high=10.0, log=False, low=-10.0, step=None)}, trial_id=1, value=None)


To get the number of trials:


len(study.trials)


100


By executing `optimize()` again, we can continue the optimization.


study.optimize(objective, n_trials=100)


To get the updated number of trials:


len(study.trials)


200


As the objective function is so easy that the last 100 trials don’t improve the result.
However, we can check the result again:


best_params = study.best_params
found_x = best_params["x"]
print(f"Found x: {found_x}, (x - 2)^2: {(found_x - 2) ** 2}")


Found x: 2.001208306754083, (x - 2)^2: 1.4600052119628892e-06


Total running time of the script: (0 minutes 0.348 seconds)


`Download Jupyter notebook: 001_first.ipynb`


`Download Python source code: 001_first.py`


`Download zipped: 001_first.zip`


Gallery generated by Sphinx-Gallery


 
 
 

 

 
 
&#169; Copyright 2018, Optuna Contributors.

 

 Built with Sphinx using a
 theme
 provided by Read the Docs.
 
 Privacy Policy.