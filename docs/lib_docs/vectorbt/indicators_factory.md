- 
- 
- 
- factory - VectorBT
- 
- 
- 
- 
- 
- 
- 
- 
- 
- Skip to content Get access to VectorBT PRO and join our quant army! 
- API 
- data 
- generic 
- indicators 
- IndicatorFactory() 
- MetaIndicatorBase() 
- nb 
- labels 
- messaging 
- ohlcv_accessors 
- portfolio 
- px_accessors 
- records 
- returns 
- root_accessors 
- signals 
- utils 
- Terms 
- IndicatorFactory() 
- MetaIndicatorBase() 
# factory module&para;
 
A factory for building new indicators with ease.
 
The indicator factory class IndicatorFactory offers a convenient way to create technical indicators of any complexity. By providing it with information such as calculation functions and the names of your inputs, parameters, and outputs, it will create a stand-alone indicator class capable of running the indicator for an arbitrary combination of your inputs and parameters. It also creates methods for signal generation and supports common pandas and parameter indexing operations.
 
Each indicator is basically a pipeline that:
 
- Accepts a list of input arrays (for example, OHLCV data) 
- Accepts a list of parameter arrays (for example, window size) 
- Accepts other relevant arguments and keyword arguments 
- For each parameter combination, performs calculation on the input arrays 
- Concatenates results into new output arrays (for example, rolling average) 
This pipeline can be well standardized, which is done by run_pipeline().
 
IndicatorFactory simplifies the usage of run_pipeline() by generating and pre-configuring a new Python class with various class methods for running the indicator.
 
Each generated class includes the following features:
 
- Accepts input arrays of any compatible shape thanks to broadcasting 
- Accepts output arrays written in-place instead of returning 
- Accepts arbitrary parameter grids 
- Supports caching and other optimizations out of the box 
- Supports pandas and parameter indexing 
- Offers helper methods for all inputs, outputs, and properties 
Consider the following price DataFrame composed of two columns, one per asset:
 
`>>> import vectorbt as vbt
>>> import numpy as np
>>> import pandas as pd
>>> from numba import njit
>>> from datetime import datetime

>>> price = pd.DataFrame({
... 'a': [1, 2, 3, 4, 5],
... 'b': [5, 4, 3, 2, 1]
... }, index=pd.Index([
... datetime(2020, 1, 1),
... datetime(2020, 1, 2),
... datetime(2020, 1, 3),
... datetime(2020, 1, 4),
... datetime(2020, 1, 5),
... ])).astype(float)
>>> price
 a b
2020-01-01 1.0 5.0
2020-01-02 2.0 4.0
2020-01-03 3.0 3.0
2020-01-04 4.0 2.0
2020-01-05 5.0 1.0
` 
For each column in the DataFrame, let's calculate a simple moving average and get its crossover with price. In particular, we want to test two different window sizes: 2 and 3.
 
## Naive approach&para;
 
A naive way of doing this:
 
`>>> ma_df = pd.DataFrame.vbt.concat(
... price.rolling(window=2).mean(),
... price.rolling(window=3).mean(),
... keys=pd.Index([2, 3], name='ma_window'))
>>> ma_df
ma_window 2 3
 a b a b
2020-01-01 NaN NaN NaN NaN
2020-01-02 1.5 4.5 NaN NaN
2020-01-03 2.5 3.5 2.0 4.0
2020-01-04 3.5 2.5 3.0 3.0
2020-01-05 4.5 1.5 4.0 2.0

>>> above_signals = (price.vbt.tile(2).vbt > ma_df)
>>> above_signals = above_signals.vbt.signals.first(after_false=True)
>>> above_signals
ma_window 2 3
 a b a b
2020-01-01 False False False False
2020-01-02 True False False False
2020-01-03 False False True False
2020-01-04 False False False False
2020-01-05 False False False False

>>> below_signals = (price.vbt.tile(2).vbt < ma_df)
>>> below_signals = below_signals.vbt.signals.first(after_false=True)
>>> below_signals
ma_window 2 3
 a b a b
2020-01-01 False False False False
2020-01-02 False True False False
2020-01-03 False False False True
2020-01-04 False False False False
2020-01-05 False False False False
` 
Now the same using IndicatorFactory:
 
`>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... param_names=['window'],
... output_names=['ma'],
... ).from_apply_func(vbt.nb.rolling_mean_nb)

>>> myind = MyInd.run(price, [2, 3])
>>> above_signals = myind.price_crossed_above(myind.ma)
>>> below_signals = myind.price_crossed_below(myind.ma)
` 
The IndicatorFactory class is used to construct indicator classes from UDFs. First, we provide all the necessary information (indicator config) to build the facade of the indicator, such as the names of inputs, parameters, and outputs, and the actual calculation function. The factory then generates a self-contained indicator class capable of running arbitrary configurations of inputs and parameters. To run any configuration, we can either use the `run` method (as we did above) or the `run_combs` method.
 
## run and run_combs methods&para;
 
The main method to run an indicator is `run`, which accepts arguments based on the config provided to the IndicatorFactory (see the example above). These arguments include input arrays, in-place output arrays, parameters, and arguments for run_pipeline().
 
The `run_combs` method takes the same inputs as the method above, but computes all combinations of passed parameters based on a combinatorial function and returns multiple instances that can be compared with each other. For example, this is useful to generate crossover signals of multiple moving averages:
 
`>>> myind1, myind2 = MyInd.run_combs(price, [2, 3, 4])

>>> myind1.ma
myind_1_window 2 3
 a b a b a b
2020-01-01 NaN NaN NaN NaN NaN NaN
2020-01-02 1.5 4.5 1.5 4.5 NaN NaN
2020-01-03 2.5 3.5 2.5 3.5 2.0 4.0
2020-01-04 3.5 2.5 3.5 2.5 3.0 3.0
2020-01-05 4.5 1.5 4.5 1.5 4.0 2.0

>>> myind2.ma
myind_2_window 3 4
 a b a b a b
2020-01-01 NaN NaN NaN NaN NaN NaN
2020-01-02 NaN NaN NaN NaN NaN NaN
2020-01-03 2.0 4.0 NaN NaN NaN NaN
2020-01-04 3.0 3.0 2.5 3.5 2.5 3.5
2020-01-05 4.0 2.0 3.5 2.5 3.5 2.5

>>> myind1.ma_crossed_above(myind2.ma)
myind_1_window 2 3
myind_2_window 3 4 4
 a b a b a b
2020-01-01 False False False False False False
2020-01-02 False False False False False False
2020-01-03 True False False False False False
2020-01-04 False False True False True False
2020-01-05 False False False False False False
` 
Its main advantage is that it doesn't need to re-compute each combination thanks to smart caching.
 
To get details on what arguments are accepted by any of the class methods, use `help`:
 
`>>> help(MyInd.run)
Help on method run:

run(price, window, short_name='custom', hide_params=None, hide_default=True, **kwargs) method of builtins.type instance
 Run `Indicator` indicator.

 * Inputs: `price`
 * Parameters: `window`
 * Outputs: `ma`

 Pass a list of parameter names as `hide_params` to hide their column levels.
 Set `hide_default` to False to show the column levels of the parameters with a default value.

 Other keyword arguments are passed to `vectorbt.indicators.factory.run_pipeline`.
` 
## Parameters&para;
 
IndicatorFactory allows definition of arbitrary parameter grids.
 
Parameters are variables that can hold one or more values. A single value can be passed as a scalar, an array, or any other object. Multiple values are passed as a list or an array (if the flag `is_array_like` is set to False for that parameter). If there are multiple parameters and each is having multiple values, their values will broadcast to a single shape:
 
` p1 p2 result
0 0 1 [(0, 1)]
1 [0, 1] [2] [(0, 2), (1, 2)]
2 [0, 1] [2, 3] [(0, 2), (1, 3)]
3 [0, 1] [2, 3, 4] error
` 
To illustrate the usage of parameters in indicators, let's build a basic indicator that returns 1 if the rolling mean is within upper and lower bounds, and -1 if it's outside:
 
`>>> @njit
... def apply_func_nb(price, window, lower, upper):
... output = np.full(price.shape, np.nan, dtype=np.float64)
... for col in range(price.shape[1]):
... for i in range(window, price.shape[0]):
... mean = np.mean(price[i - window:i, col])
... output[i, col] = lower < mean < upper
... return output

>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... param_names=['window', 'lower', 'upper'],
... output_names=['output']
... ).from_apply_func(apply_func_nb)
` 
By default, when `per_column` is set to False, each parameter is applied to the entire input.
 
One parameter combination:
 
`>>> MyInd.run(
... price,
... window=2,
... lower=3,
... upper=5
... ).output
custom_window 2
custom_lower 3
custom_upper 5
 a b
2020-01-01 NaN NaN
2020-01-02 NaN NaN
2020-01-03 0.0 1.0
2020-01-04 0.0 1.0
2020-01-05 1.0 0.0
` 
Multiple parameter combinations:
 
`>>> MyInd.run(
... price,
... window=[2, 3],
... lower=3,
... upper=5
... ).output
custom_window 2 3
custom_lower 3 3
custom_upper 5 5
 a b a b
2020-01-01 NaN NaN NaN NaN
2020-01-02 NaN NaN NaN NaN
2020-01-03 0.0 1.0 NaN NaN
2020-01-04 0.0 1.0 0.0 1.0
2020-01-05 1.0 0.0 0.0 0.0
` 
Product of parameter combinations:
 
`>>> MyInd.run(
... price,
... window=[2, 3],
... lower=[3, 4],
... upper=5,
... param_product=True
... ).output
custom_window 2 3
custom_lower 3 4 3 4
custom_upper 5 5 5 5
 a b a b a b a b
2020-01-01 NaN NaN NaN NaN NaN NaN NaN NaN
2020-01-02 NaN NaN NaN NaN NaN NaN NaN NaN
2020-01-03 0.0 1.0 0.0 1.0 NaN NaN NaN NaN
2020-01-04 0.0 1.0 0.0 0.0 0.0 1.0 0.0 0.0
2020-01-05 1.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
` 
Multiple parameter combinations, one per column:
 
`>>> MyInd.run(
... price,
... window=[2, 3],
... lower=[3, 4],
... upper=5,
... per_column=True
... ).output
custom_window 2 3
custom_lower 3 4
custom_upper 5 5
 a b
2020-01-01 NaN NaN
2020-01-02 NaN NaN
2020-01-03 0.0 NaN
2020-01-04 0.0 0.0
2020-01-05 1.0 0.0
` 
Parameter defaults can be passed directly to the IndicatorFactory.from_custom_func() and IndicatorFactory.from_apply_func(), and overridden in the run method:
 
`>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... param_names=['window', 'lower', 'upper'],
... output_names=['output']
... ).from_apply_func(apply_func_nb, window=2, lower=3, upper=4)

>>> MyInd.run(price, upper=5).output
custom_window 2
custom_lower 3
custom_upper 5
 a b
2020-01-01 NaN NaN
2020-01-02 NaN NaN
2020-01-03 0.0 1.0
2020-01-04 0.0 1.0
2020-01-05 1.0 0.0
` 
Some parameters are meant to be defined per row, column, or element of the input. By default, if we pass the parameter value as an array, the indicator will treat this array as a list of multiple values - one per input. To make the indicator view this array as a single value, set the flag `is_array_like` to True in `param_settings`. Also, to automatically broadcast the passed scalar/array to the input shape, set `bc_to_input` to True, 0 (index axis), or 1 (column axis).
 
In our example, the parameter `window` can broadcast per column, and both parameters `lower` and `upper` can broadcast per element:
 
`>>> @njit
... def apply_func_nb(price, window, lower, upper):
... output = np.full(price.shape, np.nan, dtype=np.float64)
... for col in range(price.shape[1]):
... for i in range(window[col], price.shape[0]):
... mean = np.mean(price[i - window[col]:i, col])
... output[i, col] = lower[i, col] < mean < upper[i, col]
... return output

>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... param_names=['window', 'lower', 'upper'],
... output_names=['output']
... ).from_apply_func(
... apply_func_nb,
... param_settings=dict(
... window=dict(is_array_like=True, bc_to_input=1, per_column=True),
... lower=dict(is_array_like=True, bc_to_input=True),
... upper=dict(is_array_like=True, bc_to_input=True)
... )
... )

>>> MyInd.run(
... price,
... window=[np.array([2, 3]), np.array([3, 4])],
... lower=np.array([1, 2]),
... upper=np.array([3, 4]),
... ).output
custom_window 2 3 4
custom_lower array_0 array_0 array_1 array_1
custom_upper array_0 array_0 array_1 array_1
 a b a b
2020-01-01 NaN NaN NaN NaN
2020-01-02 NaN NaN NaN NaN
2020-01-03 1.0 NaN NaN NaN
2020-01-04 1.0 0.0 1.0 NaN
2020-01-05 0.0 1.0 0.0 1.0
` 
Broadcasting a huge number of parameters to the input shape can consume lots of memory, especially when the array materializes. Luckily, vectorbt implements flexible broadcasting, which preserves the original dimensions of the parameter. This requires two changes: setting `keep_raw` to True in `broadcast_kwargs` and passing `flex_2d` to the apply function.
 
There are two configs in vectorbt.indicators.configs exactly for this purpose: one for column-wise broadcasting and one for element-wise broadcasting:
 
`>>> from vectorbt.base.reshape_fns import flex_select_auto_nb
>>> from vectorbt.indicators.configs import flex_col_param_config, flex_elem_param_config

>>> @njit
... def apply_func_nb(price, window, lower, upper, flex_2d):
... output = np.full(price.shape, np.nan, dtype=np.float64)
... for col in range(price.shape[1]):
... _window = flex_select_auto_nb(window, 0, col, flex_2d)
... for i in range(_window, price.shape[0]):
... _lower = flex_select_auto_nb(lower, i, col, flex_2d)
... _upper = flex_select_auto_nb(upper, i, col, flex_2d)
... mean = np.mean(price[i - _window:i, col])
... output[i, col] = _lower < mean < _upper
... return output

>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... param_names=['window', 'lower', 'upper'],
... output_names=['output']
... ).from_apply_func(
... apply_func_nb,
... param_settings=dict(
... window=flex_col_param_config,
... lower=flex_elem_param_config,
... upper=flex_elem_param_config
... ),
... pass_flex_2d=True
... )
` 
Both bound parameters can now be passed as a scalar (value per whole input), a 1-dimensional array (value per row or column, depending upon whether input is a Series or a DataFrame), a 2-dimensional array (value per element), or a list of any of those. This allows for the highest parameter flexibility at the lowest memory cost.
 
For example, let's build a grid of two parameter combinations, each being one window size per column and both bounds per element:
 
`>>> MyInd.run(
... price,
... window=[np.array([2, 3]), np.array([3, 4])],
... lower=price.values - 3,
... upper=price.values + 3,
... ).output
custom_window 2 3 4
custom_lower array_0 array_0 array_1 array_1
custom_upper array_0 array_0 array_1 array_1
 a b a b
2020-01-01 NaN NaN NaN NaN
2020-01-02 NaN NaN NaN NaN
2020-01-03 1.0 NaN NaN NaN
2020-01-04 1.0 1.0 1.0 NaN
2020-01-05 1.0 1.0 1.0 1.0
` 
Indicators can also be parameterless. See OBV.
 
## Inputs&para;
 
IndicatorFactory supports passing none, one, or multiple inputs. If multiple inputs are passed, it tries to broadcast them into a single shape.
 
Remember that in vectorbt each column means a separate backtest instance. That's why in order to use multiple pieces of information, such as open, high, low, close, and volume, we need to provide them as separate pandas objects rather than a single DataFrame.
 
Let's create a parameterless indicator that measures the position of the close price within each bar:
 
`>>> @njit
... def apply_func_nb(high, low, close):
... return (close - low) / (high - low)

>>> MyInd = vbt.IndicatorFactory(
... input_names=['high', 'low', 'close'],
... output_names=['output']
... ).from_apply_func(apply_func_nb)

>>> MyInd.run(price + 1, price - 1, price).output
 a b
2020-01-01 0.5 0.5
2020-01-02 0.5 0.5
2020-01-03 0.5 0.5
2020-01-04 0.5 0.5
2020-01-05 0.5 0.5
` 
To demonstrate broadcasting, let's pass high as a DataFrame, low as a Series, and close as a scalar:
 
`>>> df = pd.DataFrame(np.random.uniform(1, 2, size=(5, 2)))
>>> sr = pd.Series(np.random.uniform(0, 1, size=5))
>>> MyInd.run(df, sr, 1).output
 0 1
0 0.960680 0.666820
1 0.400646 0.528456
2 0.093467 0.134777
3 0.037210 0.102411
4 0.529012 0.652602
` 
By default, if a Series was passed, it's automatically expanded into a 2-dimensional array. To keep it as 1-dimensional, set `to_2d` to False.
 
Similar to parameters, we can also define defaults for inputs. In addition to using scalars and arrays as default values, we can reference other inputs:
 
`>>> @njit
... def apply_func_nb(ts1, ts2, ts3):
... return ts1 + ts2 + ts3

>>> MyInd = vbt.IndicatorFactory(
... input_names=['ts1', 'ts2', 'ts3'],
... output_names=['output']
... ).from_apply_func(apply_func_nb, ts2='ts1', ts3='ts1')

>>> MyInd.run(price).output
 a b
2020-01-01 3.0 15.0
2020-01-02 6.0 12.0
2020-01-03 9.0 9.0
2020-01-04 12.0 6.0
2020-01-05 15.0 3.0

>>> MyInd.run(price, ts2=price * 2).output
 a b
2020-01-01 4.0 20.0
2020-01-02 8.0 16.0
2020-01-03 12.0 12.0
2020-01-04 16.0 8.0
2020-01-05 20.0 4.0
` 
What if an indicator doesn't take any input arrays? In that case, we can force the user to at least provide the input shape. Let's define a generator that emulates random returns and generates synthetic price:
 
`>>> @njit
... def apply_func_nb(input_shape, start, mu, sigma):
... rand_returns = np.random.normal(mu, sigma, input_shape)
... return start * vbt.nb.nancumprod_nb(rand_returns + 1)

>>> MyInd = vbt.IndicatorFactory(
... param_names=['start', 'mu', 'sigma'],
... output_names=['output']
... ).from_apply_func(
... apply_func_nb,
... require_input_shape=True,
... seed=42
... )

>>> MyInd.run(price.shape, 100, 0, 0.01).output
custom_start 100
custom_mu 0
custom_sigma 0.01 0.01
0 100.496714 99.861736
1 101.147620 101.382660
2 100.910779 101.145285
3 102.504375 101.921510
4 102.023143 102.474495
` 
We can also supply pandas meta such as `input_index` and `input_columns` to the run method:
 
`>>> MyInd.run(
... price.shape, 100, 0, 0.01,
... input_index=price.index, input_columns=price.columns
... ).output
custom_start 100
custom_mu 0
custom_sigma 0.01 0.01
 a b
2020-01-01 100.496714 99.861736
2020-01-02 101.147620 101.382660
2020-01-03 100.910779 101.145285
2020-01-04 102.504375 101.921510
2020-01-05 102.023143 102.474495
` 
One can even build input-less indicator that decides on the output shape dynamically:
 
`>>> from vectorbt.base.combine_fns import apply_and_concat_one

>>> def apply_func(i, ps, input_shape):
... out = np.full(input_shape, 0)
... out[:ps[i]] = 1
... return out

>>> def custom_func(ps):
... input_shape = (np.max(ps),)
... return apply_and_concat_one(len(ps), apply_func, ps, input_shape)

>>> MyInd = vbt.IndicatorFactory(
... param_names=['p'],
... output_names=['output']
... ).from_custom_func(custom_func)

>>> MyInd.run([1, 2, 3, 4, 5]).output
custom_p 1 2 3 4 5
0 1 1 1 1 1
1 0 1 1 1 1
2 0 0 1 1 1
3 0 0 0 1 1
4 0 0 0 0 1
` 
## Outputs&para;
 
There are two types of outputs: regular and in-place outputs:
 
- Regular outputs are one or more arrays returned by the function. Each should have an exact same shape and match the number of columns in the input multiplied by the number of parameter values. 
- In-place outputs are not returned but modified in-place. They broadcast together with inputs and are passed to the calculation function as a list, one per parameter. 
Two regular outputs:
 
`>>> @njit
... def apply_func_nb(price):
... return price - 1, price + 1

>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... output_names=['out1', 'out2']
... ).from_apply_func(apply_func_nb)

>>> myind = MyInd.run(price)
>>> pd.testing.assert_frame_equal(myind.out1, myind.price - 1)
>>> pd.testing.assert_frame_equal(myind.out2, myind.price + 1)
` 
One regular output and one in-place output:
 
`>>> @njit
... def apply_func_nb(price, in_out2):
... in_out2[:] = price + 1
... return price - 1

>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... output_names=['out1'],
... in_output_names=['in_out2']
... ).from_apply_func(apply_func_nb)

>>> myind = MyInd.run(price)
>>> pd.testing.assert_frame_equal(myind.out1, myind.price - 1)
>>> pd.testing.assert_frame_equal(myind.in_out2, myind.price + 1)
` 
Two in-place outputs:
 
`>>> @njit
... def apply_func_nb(price, in_out1, in_out2):
... in_out1[:] = price - 1
... in_out2[:] = price + 1

>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... in_output_names=['in_out1', 'in_out2']
... ).from_apply_func(apply_func_nb)

>>> myind = MyInd.run(price)
>>> pd.testing.assert_frame_equal(myind.in_out1, myind.price - 1)
>>> pd.testing.assert_frame_equal(myind.in_out2, myind.price + 1)
` 
By default, in-place outputs are created as empty arrays with uninitialized values. This allows creation of optional outputs that, if not written, do not occupy much memory. Since not all outputs are meant to be of data type `float`, we can pass `dtype` in the `in_output_settings`.
 
`>>> @njit
... def apply_func_nb(price, in_out):
... in_out[:] = price > np.mean(price)

>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... in_output_names=['in_out']
... ).from_apply_func(
... apply_func_nb,
... in_output_settings=dict(in_out=dict(dtype=bool))
... )

>>> MyInd.run(price).in_out
 a b
2020-01-01 False True
2020-01-02 False True
2020-01-03 False False
2020-01-04 True False
2020-01-05 True False
` 
Another advantage of in-place outputs is that we can provide their initial state:
 
`>>> @njit
... def apply_func_nb(price, in_out1, in_out2):
... in_out1[:] = in_out1 + price
... in_out2[:] = in_out2 + price

>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... in_output_names=['in_out1', 'in_out2']
... ).from_apply_func(
... apply_func_nb,
... in_out1=100,
... in_out2='price'
... )

>>> myind = MyInd.run(price)
>>> myind.in_out1
 a b
2020-01-01 101 105
2020-01-02 102 104
2020-01-03 103 103
2020-01-04 104 102
2020-01-05 105 101
>>> myind.in_out2
 a b
2020-01-01 2.0 10.0
2020-01-02 4.0 8.0
2020-01-03 6.0 6.0
2020-01-04 8.0 4.0
2020-01-05 10.0 2.0
` 
## Without Numba&para;
 
It's also possible to supply a function that is not Numba-compiled. This is handy when working with third-party libraries (see the implementation of IndicatorFactory.from_talib()). Additionally, we can set `keep_pd` to True to pass all inputs as pandas objects instead of raw NumPy arrays.
 
Note
 
Already broadcasted pandas meta will be provided; that is, each input array will have the same index and columns.
 
Let's demonstrate this by wrapping a basic composed pandas_ta strategy:
 
`>>> import pandas_ta # or import pandas_ta_classic as pandas_ta

>>> def apply_func(open, high, low, close, volume, ema_len, linreg_len):
... df = pd.DataFrame(dict(open=open, high=high, low=low, close=close, volume=volume))
... df.ta.strategy(pandas_ta.Strategy("MyStrategy", [
... dict(kind='ema', length=ema_len),
... dict(kind='linreg', close='EMA_' + str(ema_len), length=linreg_len)
... ]))
... return tuple([df.iloc[:, i] for i in range(5, len(df.columns))])

>>> MyInd = vbt.IndicatorFactory(
... input_names=['open', 'high', 'low', 'close', 'volume'],
... param_names=['ema_len', 'linreg_len'],
... output_names=['ema', 'ema_linreg']
... ).from_apply_func(
... apply_func,
... keep_pd=True,
... to_2d=False
... )

>>> my_ind = MyInd.run(
... ohlcv['Open'],
... ohlcv['High'],
... ohlcv['Low'],
... ohlcv['Close'],
... ohlcv['Volume'],
... ema_len=5,
... linreg_len=[8, 9, 10]
... )

>>> my_ind.ema_linreg
custom_ema_len 5
custom_linreg_len 8 9 10
date
2021-02-02 NaN NaN NaN
2021-02-03 NaN NaN NaN
2021-02-04 NaN NaN NaN
2021-02-05 NaN NaN NaN
2021-02-06 NaN NaN NaN
... ... ... ...
2021-02-25 52309.302811 52602.005326 52899.576568
2021-02-26 50797.264793 51224.188381 51590.825690
2021-02-28 49217.904905 49589.546052 50066.206828
2021-03-01 48316.305403 48553.540713 48911.701664
2021-03-02 47984.395969 47956.885953 48150.929668
` 
In the example above, only one Series per open, high, low, close, and volume can be passed. To enable the indicator to process two-dimensional data, set `to_2d` to True and create a loop over each column in the `apply_func`.
 
Hint
 
Writing a native Numba-compiled code may provide a performance that is magnitudes higher than that offered by libraries that work on pandas.
 
## Raw outputs and caching&para;
 
IndicatorFactory re-uses calculation artifacts whenever possible. Since it was originally designed for hyperparameter optimization and there are times when parameter values gets repeated, prevention of processing the same parameter over and over again is inevitable for good performance. For instance, when the `run_combs` method is being used and `run_unique` is set to True, it first calculates the raw outputs of all unique parameter combinations and then uses them to build outputs for the whole parameter grid.
 
Let's first take a look at a typical raw output by setting `return_raw` to True:
 
`>>> raw = vbt.MA.run(price, 2, [False, True], return_raw=True)
>>> raw
([array([[ nan, nan, nan, nan],
 [1.5 , 4.5 , 1.66666667, 4.33333333],
 [2.5 , 3.5 , 2.55555556, 3.44444444],
 [3.5 , 2.5 , 3.51851852, 2.48148148],
 [4.5 , 1.5 , 4.50617284, 1.49382716]])],
 [(2, False), (2, True)],
 2,
 [])
` 
It consists of a list of the returned output arrays, a list of the zipped parameter combinations, the number of input columns, and other objects returned along with output arrays but not listed in `output_names`. The next time we decide to run the indicator on a subset of the parameters above, we can simply pass this tuple as the `use_raw` argument. This won't call the calculation function and will throw an error if some of the requested parameter combinations cannot be found in `raw`.
 
`>>> vbt.MA.run(price, 2, True, use_raw=raw).ma
ma_window 2
ma_ewm True
 a b
2020-01-01 NaN NaN
2020-01-02 1.666667 4.333333
2020-01-03 2.555556 3.444444
2020-01-04 3.518519 2.481481
2020-01-05 4.506173 1.493827
` 
Here is how the performance compares when repeatedly running the same parameter combination with and without `run_unique`:
 
`>>> a = np.random.uniform(size=(1000,))

>>> %timeit vbt.MA.run(a, np.full(1000, 2), run_unique=False)
73.4 ms ± 4.76 ms per loop (mean ± std. dev. of 7 runs, 1 loop each)

>>> %timeit vbt.MA.run(a, np.full(1000, 2), run_unique=True)
8.99 ms ± 114 µs per loop (mean ± std. dev. of 7 runs, 100 loops each)
` 
Note
 
`run_unique` is disabled by default.
 
Enable `run_unique` if input arrays have few columns and there are tons of repeated parameter combinations. Disable `run_unique` if input arrays are very wide, if two identical parameter combinations can lead to different results, or when requesting raw output, cache, or additional outputs outside of `output_names`.
 
Another performance enhancement can be introduced by caching, which has to be implemented by the user. The class method IndicatorFactory.from_apply_func() has an argument `cache_func`, which is called prior to the main calculation.
 
Consider the following scenario: we want to compute the relative distance between two expensive rolling windows. We have already decided on the value for the first window, and want to test thousands of values for the second window. Without caching, and even with `run_unique` enabled, the first rolling window will be re-calculated over and over again and waste our resources:
 
`>>> @njit
... def roll_mean_expensive_nb(price, w):
... for i in range(100):
... out = vbt.nb.rolling_mean_nb(price, w)
... return out

>>> @njit
... def apply_func_nb(price, w1, w2):
... roll_mean1 = roll_mean_expensive_nb(price, w1)
... roll_mean2 = roll_mean_expensive_nb(price, w2)
... return (roll_mean2 - roll_mean1) / roll_mean1

>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... param_names=['w1', 'w2'],
... output_names=['output'],
... ).from_apply_func(apply_func_nb)

>>> MyInd.run(price, 2, 3).output
custom_w1 2
custom_w2 3
 a b
2020-01-01 NaN NaN
2020-01-02 NaN NaN
2020-01-03 -0.200000 0.142857
2020-01-04 -0.142857 0.200000
2020-01-05 -0.111111 0.333333

>>> %timeit MyInd.run(price, 2, np.arange(2, 1000))
264 ms ± 3.22 ms per loop (mean ± std. dev. of 7 runs, 1 loop each)
` 
To avoid this, let's cache all unique rolling windows:
 
`>>> @njit
... def cache_func_nb(price, ws1, ws2):
... cache_dict = dict()
... ws = ws1.copy()
... ws.extend(ws2)
... for i in range(len(ws)):
... h = hash((ws[i]))
... if h not in cache_dict:
... cache_dict[h] = roll_mean_expensive_nb(price, ws[i])
... return cache_dict

>>> @njit
... def apply_func_nb(price, w1, w2, cache_dict):
... return (cache_dict[hash(w2)] - cache_dict[hash(w1)]) / cache_dict[hash(w1)]

>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... param_names=['w1', 'w2'],
... output_names=['output'],
... ).from_apply_func(apply_func_nb, cache_func=cache_func_nb)

>>> MyInd.run(price, 2, 3).output
custom_w1 2
custom_w2 3
 a b
2020-01-01 NaN NaN
2020-01-02 NaN NaN
2020-01-03 -0.200000 0.142857
2020-01-04 -0.142857 0.200000
2020-01-05 -0.111111 0.333333

>>> %timeit MyInd.run(price, 2, np.arange(2, 1000))
145 ms ± 4.55 ms per loop (mean ± std. dev. of 7 runs, 10 loops each)
` 
We have cut down the processing time almost in half.
 
Similar to raw outputs, we can force IndicatorFactory to return the cache, so it can be used in other calculations or even indicators. The clear advantage of this approach is that we don't rely on some fixed set of parameter combinations any more, but on the values of each parameter, which gives us more granularity in managing performance.
 
`>>> cache = MyInd.run(price, 2, np.arange(2, 1000), return_cache=True)

>>> %timeit MyInd.run(price, np.arange(2, 1000), np.arange(2, 1000), use_cache=cache)
30.1 ms ± 2 ms per loop (mean ± std. dev. of 7 runs, 10 loops each)
` 
## Custom properties and methods&para;
 
Use `custom_output_props` argument when constructing an indicator to define lazy outputs - outputs that are processed only when explicitly called. They will become cached properties and, in contrast to regular outputs, they can have an arbitrary shape. For example, let's attach a property that will calculate the distance between the moving average and the price.
 
`>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... param_names=['window'],
... output_names=['ma'],
... custom_output_props=dict(distance=lambda self: (self.price - self.ma) / self.ma)
... ).from_apply_func(vbt.nb.rolling_mean_nb)

>>> MyInd.run(price, [2, 3]).distance
custom_window 2 3
 a b a b
2020-01-01 NaN NaN NaN NaN
2020-01-02 0.333333 -0.111111 NaN NaN
2020-01-03 0.200000 -0.142857 0.500000 -0.250000
2020-01-04 0.142857 -0.200000 0.333333 -0.333333
2020-01-05 0.111111 -0.333333 0.250000 -0.500000
` 
Another way of defining own properties and methods is subclassing:
 
`>>> class MyIndExtended(MyInd):
... def plot(self, column=None, **kwargs):
... self_col = self.select_one(column=column, group_by=False)
... return self.ma.vbt.plot(**kwargs)

>>> MyIndExtended.run(price, [2, 3])[(2, 'a')].plot()
` 

 
## Helper properties and methods&para;
 
For all in `input_names`, `in_output_names`, `output_names`, and `custom_output_props`, IndicatorFactory will create a bunch of comparison and combination methods, such as for generating signals. What kind of methods are created can be regulated using `dtype` in the `attr_settings` dictionary.
 
`>>> from collections import namedtuple

>>> MyEnum = namedtuple('MyEnum', ['one', 'two'])(0, 1)

>>> def apply_func_nb(price):
... out_float = np.empty(price.shape, dtype=np.float64)
... out_bool = np.empty(price.shape, dtype=np.bool_)
... out_enum = np.empty(price.shape, dtype=np.int64)
... return out_float, out_bool, out_enum

>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... output_names=['out_float', 'out_bool', 'out_enum'],
... attr_settings=dict(
... out_float=dict(dtype=np.float64),
... out_bool=dict(dtype=np.bool_),
... out_enum=dict(dtype=MyEnum)
... )).from_apply_func(apply_func_nb)

>>> myind = MyInd.run(price)
>>> dir(myind)
[
 ...
 'out_bool',
 'out_bool_and',
 'out_bool_or',
 'out_bool_stats',
 'out_bool_xor',
 'out_enum',
 'out_enum_readable',
 'out_enum_stats',
 'out_float',
 'out_float_above',
 'out_float_below',
 'out_float_equal',
 'out_float_stats',
 ...
 'price',
 'price_above',
 'price_below',
 'price_equal',
 'price_stats',
 ...
]
` 
Each of these methods and properties are created for sheer convenience: to easily combine boolean arrays using logical rules and to compare numeric arrays. All operations are done strictly using NumPy. Another advantage is utilization of vectorbt's own broadcasting, such that one can combine inputs and outputs with an arbitrary array-like object, given their shapes can broadcast together.
 
We can also do comparison with multiple objects at once by passing them as a tuple/list:
 
`>>> myind.price_above([1.5, 2.5])
custom_price_above 1.5 2.5
 a b a b
2020-01-01 False True False True
2020-01-02 True True False True
2020-01-03 True True True True
2020-01-04 True True True False
2020-01-05 True False True False
` 
## Indexing&para;
 
IndicatorFactory attaches pandas indexing to the indicator class thanks to ArrayWrapper. Supported are `iloc`, `loc`, `*param_name*_loc`, `xs`, and `__getitem__`.
 
This makes possible accessing rows and columns by labels, integer positions, and parameters.
 
`>>> ma = vbt.MA.run(price, [2, 3])

>>> ma[(2, 'b')]
<vectorbt.indicators.basic.MA at 0x7fe4d10ddcc0>

>>> ma[(2, 'b')].ma
2020-01-01 NaN
2020-01-02 4.5
2020-01-03 3.5
2020-01-04 2.5
2020-01-05 1.5
Name: (2, b), dtype: float64

>>> ma.window_loc[2].ma
 a b
2020-01-01 NaN NaN
2020-01-02 1.5 4.5
2020-01-03 2.5 3.5
2020-01-04 3.5 2.5
2020-01-05 4.5 1.5
` 
## TA-Lib&para;
 
Indicator factory also provides a class method IndicatorFactory.from_talib() that can be used to wrap any function from TA-Lib. It automatically fills all the necessary information, such as input, parameter and output names.
 
## Stats&para;
 
Hint
 
See StatsBuilderMixin.stats().
 
We can attach metrics to any new indicator class:
 
`>>> @njit
... def apply_func_nb(price):
... return price ** 2, price ** 3

>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... output_names=['out1', 'out2'],
... metrics=dict(
... sum_diff=dict(
... calc_func=lambda self: self.out2.sum() - self.out1.sum()
... )
... )
... ).from_apply_func(
... apply_func_nb
... )

>>> myind = MyInd.run(price)
>>> myind.stats(column='a')
sum_diff 170.0
Name: a, dtype: float64
` 
## Plots&para;
 
Hint
 
See PlotsBuilderMixin.plots().
 
Similarly to stats, we can attach subplots to any new indicator class:
 
`>>> @njit
... def apply_func_nb(price):
... return price ** 2, price ** 3

>>> def plot_outputs(out1, out2, column=None, fig=None):
... fig = out1[column].rename('out1').vbt.plot(fig=fig)
... fig = out2[column].rename('out2').vbt.plot(fig=fig)

>>> MyInd = vbt.IndicatorFactory(
... input_names=['price'],
... output_names=['out1', 'out2'],
... subplots=dict(
... plot_outputs=dict(
... plot_func=plot_outputs,
... resolve_out1=True,
... resolve_out2=True
... )
... )
... ).from_apply_func(
... apply_func_nb
... )

>>> myind = MyInd.run(price)
>>> myind.plots(column='a')
` 

 
## build_columns function&para;
 
`build_columns(
 param_list,
 input_columns,
 level_names=None,
 hide_levels=None,
 param_settings=None,
 per_column=False,
 ignore_default=False,
 **kwargs
)
` 
For each parameter in `param_list`, create a new column level with parameter values and stack it on top of `input_columns`.
 
Returns a list of parameter indexes and new columns.
 
## combine_objs function&para;
 
`combine_objs(
 obj,
 other,
 *args,
 level_name=None,
 keys=None,
 allow_multiple=True,
 **kwargs
)
` 
Combines/compares `obj` to `other`, for example, to generate signals.
 
Both will broadcast together. Pass `other` as a tuple or a list to compare with multiple arguments. In this case, a new column level will be created with the name `level_name`.
 
See BaseAccessor.combine().
 
## params_to_list function&para;
 
`params_to_list(
 params,
 is_tuple,
 is_array_like
)
` 
Cast parameters to a list.
 
## prepare_params function&para;
 
`prepare_params(
 param_list,
 param_settings=None,
 input_shape=None,
 to_2d=False
)
` 
Prepare parameters.
 
## run_pipeline function&para;
 
`run_pipeline(
 num_ret_outputs,
 custom_func,
 *args,
 require_input_shape=False,
 input_shape=None,
 input_index=None,
 input_columns=None,
 input_list=None,
 in_output_list=None,
 in_output_settings=None,
 broadcast_kwargs=None,
 param_list=None,
 param_product=False,
 param_settings=None,
 run_unique=False,
 silence_warnings=False,
 per_column=False,
 pass_col=False,
 keep_pd=False,
 to_2d=True,
 as_lists=False,
 pass_input_shape=False,
 pass_flex_2d=False,
 pass_seed=False,
 level_names=None,
 hide_levels=None,
 stacking_kwargs=None,
 return_raw=False,
 use_raw=None,
 wrapper_kwargs=None,
 seed=None,
 **kwargs
)
` 
A pipeline for running an indicator, used by IndicatorFactory.
 
Args
 `num_ret_outputs` :&ensp;`int` The number of output arrays returned by `custom_func`. `custom_func` :&ensp;`callable` 
A custom calculation function.
 
See IndicatorFactory.from_custom_func().
 `*args` Arguments passed to the `custom_func`. `require_input_shape` :&ensp;`bool` 
Whether to input shape is required.
 
Will set `pass_input_shape` to True and raise an error if `input_shape` is None.
 `input_shape` :&ensp;`tuple` 
Shape to broadcast each input to.
 
Can be passed to `custom_func`. See `pass_input_shape`.
 `input_index` :&ensp;`index_like` 
Sets index of each input.
 
Can be used to label index if no inputs passed.
 `input_columns` :&ensp;`index_like` 
Sets columns of each input.
 
Can be used to label columns if no inputs passed.
 `input_list` :&ensp;`list` of `array_like` A list of input arrays. `in_output_list` :&ensp;`list` of `array_like` 
A list of in-place output arrays.
 
If an array should be generated, pass None.
 `in_output_settings` :&ensp;`dict` or `list` of `dict` 
Settings corresponding to each in-place output.
 
Following keys are accepted:
 
- `dtype`: Create this array using this data type and `np.empty`. Default is None. `broadcast_kwargs` :&ensp;`dict` Keyword arguments passed to broadcast() to broadcast inputs. `param_list` :&ensp;`list` of `any` 
A list of parameters.
 
Each element is either an array-like object or a single value of any type.
 `param_product` :&ensp;`bool` Whether to build a Cartesian product out of all parameters. `param_settings` :&ensp;`dict` or `list` of `dict` 
Settings corresponding to each parameter.
 
Following keys are accepted:
 
- `dtype`: If data type is an enumerated type or other mapping, and a string as parameter value was passed, will convert it first. 
- `is_tuple`: If tuple was passed, it will be considered as a single value. To treat it as multiple values, pack it into a list. 
- `is_array_like`: If array-like object was passed, it will be considered as a single value. To treat it as multiple values, pack it into a list. 
- `bc_to_input`: Whether to broadcast parameter to input size. You can also broadcast parameter to an axis by passing an integer. 
- `broadcast_kwargs`: Keyword arguments passed to broadcast(). 
- `per_column`: Whether each parameter value can be split per column such that it can be better reflected in a multi-index. Does not affect broadcasting. `run_unique` :&ensp;`bool` 
Whether to run only on unique parameter combinations.
 
Disable if two identical parameter combinations can lead to different results (e.g., due to randomness) or if inputs are large and `custom_func` is fast.
 
Note
 
Cache, raw output, and output objects outside of `num_ret_outputs` will be returned for unique parameter combinations only.
 `silence_warnings` :&ensp;`bool` Whether to hide warnings such as coming from `run_unique`. `per_column` :&ensp;`bool` 
Whether to split the DataFrame into Series, one per column, and run `custom_func` on each Series.
 
Each list of parameter values will broadcast to the number of columns and each parameter value will be applied per Series rather than per DataFrame. Input shape must be known beforehand.
 `pass_col` :&ensp;`bool` Whether to pass column index as keyword argument if `per_column` is set to True. `keep_pd` :&ensp;`bool` Whether to keep inputs as pandas objects, otherwise convert to NumPy arrays. `to_2d` :&ensp;`bool` Whether to reshape inputs to 2-dim arrays, otherwise keep as-is. `as_lists` :&ensp;`bool` 
Whether to pass inputs and parameters to `custom_func` as lists.
 
If `custom_func` is Numba-compiled, passes tuples.
 `pass_input_shape` :&ensp;`bool` Whether to pass `input_shape` to `custom_func` as keyword argument. `pass_flex_2d` :&ensp;`bool` Whether to pass `flex_2d` to `custom_func` as keyword argument. `pass_seed` :&ensp;`bool` Whether to pass `seed` to `custom_func` as keyword argument. `level_names` :&ensp;`list` of `str` 
A list of column level names corresponding to each parameter.
 
Should have the same length as `param_list`.
 `hide_levels` :&ensp;`list` of `int` A list of indices of parameter levels to hide. `stacking_kwargs` :&ensp;`dict` Keyword arguments passed to repeat_index(), tile_index(), and stack_indexes() when stacking parameter and input column levels. `return_raw` :&ensp;`bool` Whether to return raw output without post-processing and hashed parameter tuples. `use_raw` :&ensp;`bool` Takes the raw results and uses them instead of running `custom_func`. `wrapper_kwargs` :&ensp;`dict` Keyword arguments passed to ArrayWrapper. `seed` :&ensp;`int` Set seed to make output deterministic. `**kwargs` 
Keyword arguments passed to the `custom_func`.
 
Some common arguments include `return_cache` to return cache and `use_cache` to use cache. Those are only applicable to `custom_func` that supports it (`custom_func` created using IndicatorFactory.from_apply_func() are supported by default).
 
Returns
 
Array wrapper, list of inputs (`np.ndarray`), input mapper (`np.ndarray`), list of outputs (`np.ndarray`), list of parameter arrays (`np.ndarray`), list of parameter mappers (`np.ndarray`), list of outputs that are outside of `num_ret_outputs`. Explanation
 
Here is a subset of tasks that the function run_pipeline() does:
 
- Takes one or multiple array objects in `input_list` and broadcasts them. 
`>>> sr = pd.Series([1, 2], index=['x', 'y'])
>>> df = pd.DataFrame([[3, 4], [5, 6]], index=['x', 'y'], columns=['a', 'b'])
>>> input_list = vbt.base.reshape_fns.broadcast(sr, df)
>>> input_list[0]
 a b
x 1 1
y 2 2
>>> input_list[1]
 a b
x 3 4
y 5 6
` 
- Takes one or multiple parameters in `param_list`, converts them to NumPy arrays and broadcasts them. 
`>>> p1, p2, p3 = 1, [2, 3, 4], [False]
>>> param_list = vbt.base.reshape_fns.broadcast(p1, p2, p3)
>>> param_list[0]
array([1, 1, 1])
>>> param_list[1]
array([2, 3, 4])
>>> param_list[2]
array([False, False, False])
` 
- Performs calculation using `custom_func` to build output arrays (`output_list`) and other objects (`other_list`, optionally). 
`>>> def custom_func(ts1, ts2, p1, p2, p3, *args, **kwargs):
... return np.hstack((
... ts1 + ts2 + p1[0] * p2[0],
... ts1 + ts2 + p1[1] * p2[1],
... ts1 + ts2 + p1[2] * p2[2],
... ))

>>> output = custom_func(*input_list, *param_list)
>>> output
array([[ 6, 7, 7, 8, 8, 9],
 [ 9, 10, 10, 11, 11, 12]])
` 
- Creates new column hierarchy based on parameters and level names. 
`>>> p1_columns = pd.Index(param_list[0], name='p1')
>>> p2_columns = pd.Index(param_list[1], name='p2')
>>> p3_columns = pd.Index(param_list[2], name='p3')
>>> p_columns = vbt.base.index_fns.stack_indexes([p1_columns, p2_columns, p3_columns])
>>> new_columns = vbt.base.index_fns.combine_indexes([p_columns, input_list[0].columns])

>>> output_df = pd.DataFrame(output, columns=new_columns)
>>> output_df
p1 1
p2 2 3 4
p3 False False False False False False
 a b a b a b
0 6 7 7 8 8 9
1 9 10 10 11 11 12
` 
- Broadcasts objects in `input_list` to match the shape of objects in `output_list` through tiling. This is done to be able to compare them and generate signals, since we cannot compare NumPy arrays that have totally different shapes, such as (2, 2) and (2, 6). 
`>>> new_input_list = [
... input_list[0].vbt.tile(len(param_list[0]), keys=p_columns),
... input_list[1].vbt.tile(len(param_list[0]), keys=p_columns)
... ]
>>> new_input_list[0]
p1 1
p2 2 3 4
p3 False False False False False False
 a b a b a b
0 1 1 1 1 1 1
1 2 2 2 2 2 2
` 
- Builds parameter mappers that will link parameters from `param_list` to columns in `input_list` and `output_list`. This is done to enable column indexing using parameter values. 
## IndicatorBase class&para;
 
`IndicatorBase(
 wrapper,
 input_list,
 input_mapper,
 in_output_list,
 output_list,
 param_list,
 mapper_list,
 short_name,
 level_names
)
` 
Indicator base class.
 
Properties should be set before instantiation.
 
Superclasses
 
- AttrResolver 
- Configured 
- Documented 
- IndexingBase 
- PandasIndexer 
- Pickleable 
- PlotsBuilderMixin 
- StatsBuilderMixin 
- Wrapping 
Inherited members
 
- AttrResolver.deep_getattr() 
- AttrResolver.post_resolve_attr() 
- AttrResolver.pre_resolve_attr() 
- AttrResolver.resolve_attr() 
- Configured.copy() 
- Configured.dumps() 
- Configured.loads() 
- Configured.replace() 
- Configured.to_doc() 
- Configured.update_config() 
- PandasIndexer.xs() 
- Pickleable.load() 
- Pickleable.save() 
- PlotsBuilderMixin.build_subplots_doc() 
- PlotsBuilderMixin.override_subplots_doc() 
- PlotsBuilderMixin.plots() 
- PlotsBuilderMixin.plots_defaults 
- StatsBuilderMixin.build_metrics_doc() 
- StatsBuilderMixin.override_metrics_doc() 
- StatsBuilderMixin.stats() 
- StatsBuilderMixin.stats_defaults 
- Wrapping.config 
- Wrapping.iloc 
- Wrapping.indexing_kwargs 
- Wrapping.loc 
- Wrapping.regroup() 
- Wrapping.resolve_self() 
- Wrapping.select_one() 
- Wrapping.select_one_from_obj() 
- Wrapping.self_aliases 
- Wrapping.wrapper 
- Wrapping.writeable_attrs 
Subclasses
 
- ATR 
- BBANDS 
- BOLB 
- FIXLB 
- FMAX 
- FMEAN 
- FMIN 
- FSTD 
- LEXLB 
- MA 
- MACD 
- MEANLB 
- MSTD 
- OBV 
- OHLCSTCX 
- OHLCSTX 
- RAND 
- RANDNX 
- RANDX 
- RPROB 
- RPROBCX 
- RPROBNX 
- RPROBX 
- RSI 
- STCX 
- STOCH 
- STX 
- TRENDLB 
### in_output_names method&para;
 
Names of the in-place output arrays.
 
### indexing_func method&para;
 
`IndicatorBase.indexing_func(
 pd_indexing_func,
 **kwargs
)
` 
Perform indexing on IndicatorBase.
 
### input_names method&para;
 
Names of the input arrays.
 
### level_names property&para;
 
Column level names corresponding to each parameter.
 
### output_flags method&para;
 
Dictionary of output flags.
 
### output_names method&para;
 
Names of the regular output arrays.
 
### param_names method&para;
 
Names of the parameters.
 
### run class method&para;
 
`IndicatorBase.run(
 *args,
 **kwargs
)
` 
Public run method.
 
### run_combs class method&para;
 
`IndicatorBase.run_combs(
 *args,
 **kwargs
)
` 
Public run combinations method.
 
### short_name property&para;
 
Name of the indicator.
 
## IndicatorFactory class&para;
 
`IndicatorFactory(
 class_name='Indicator',
 class_docstring='',
 module_name='vectorbt.indicators.factory',
 short_name=None,
 prepend_name=True,
 input_names=None,
 param_names=None,
 in_output_names=None,
 output_names=None,
 output_flags=None,
 custom_output_props=None,
 attr_settings=None,
 metrics=None,
 stats_defaults=None,
 subplots=None,
 plots_defaults=None
)
` 
A factory for creating new indicators.
 
Initialize IndicatorFactory to create a skeleton and then use a class method such as IndicatorFactory.from_custom_func() to bind a calculation function to the skeleton.
 
Args
 `class_name` :&ensp;`str` Name for the created indicator class. `class_docstring` :&ensp;`str` Docstring for the created indicator class. `module_name` :&ensp;`str` Specify the module the class originates from. `short_name` :&ensp;`str` 
A short name of the indicator.
 
Defaults to lower-case `class_name`.
 `prepend_name` :&ensp;`bool` Whether to prepend `short_name` to each parameter level. `input_names` :&ensp;`list` of `str` A list of names of input arrays. `param_names` :&ensp;`list` of `str` A list of names of parameters. `in_output_names` :&ensp;`list` of `str` 
A list of names of in-place output arrays.
 
An in-place output is an output that is not returned but modified in-place. Some advantages of such outputs include:
 
1) they don't need to be returned, 2) they can be passed between functions as easily as inputs, 3) they can be provided with already allocated data to safe memory, 4) if data or default value are not provided, they are created empty to not occupy memory.
 `output_names` :&ensp;`list` of `str` A list of names of output arrays. `output_flags` :&ensp;`dict` A dictionary of in-place and regular output flags. `custom_output_props` :&ensp;`dict` A dictionary with user-defined functions that will be bound to the indicator class and wrapped with `@cached_property`. `attr_settings` :&ensp;`dict` 
A dictionary of settings by attribute name.
 
Attributes can be `input_names`, `in_output_names`, `output_names` and `custom_output_props`.
 
Following keys are accepted:
 
- `dtype`: Data type used to determine which methods to generate around this attribute. Set to None to disable. Default is `np.float64`. Can be set to instance of `collections.namedtuple` acting as enumerated type, or any other mapping; It will then create a property with suffix `readable` that contains data in a string format. `metrics` :&ensp;`dict` 
Metrics supported by StatsBuilderMixin.stats().
 
If dict, will be converted to Config.
 `stats_defaults` :&ensp;`callable` or `dict` 
Defaults for StatsBuilderMixin.stats().
 
If dict, will be converted into a property.
 `subplots` :&ensp;`dict` 
Subplots supported by PlotsBuilderMixin.plots().
 
If dict, will be converted to Config.
 `plots_defaults` :&ensp;`callable` or `dict` 
Defaults for PlotsBuilderMixin.plots().
 
If dict, will be converted into a property.
 
Note
 
The `__init__` method is not used for running the indicator, for this use `run`. The reason for this is indexing, which requires a clean `__init__` method for creating a new indicator object with newly indexed attributes.
 
Subclasses
 
- SignalFactory 
### find_ta_indicator class method&para;
 
`IndicatorFactory.find_ta_indicator(
 cls_name
)
` 
Get ta indicator class by its name.
 
### from_apply_func method&para;
 
`IndicatorFactory.from_apply_func(
 apply_func,
 cache_func=None,
 pass_packed=False,
 kwargs_to_args=None,
 numba_loop=False,
 pass_seed=False,
 **kwargs
)
` 
Build indicator class around a custom apply function.
 
In contrast to IndicatorFactory.from_custom_func(), this method handles a lot of things for you, such as caching, parameter selection, and concatenation. Your part is writing a function `apply_func` that accepts a selection of parameters (single values as opposed to multiple values in IndicatorFactory.from_custom_func()) and does the calculation. It then automatically concatenates the resulting arrays into a single array per output.
 
While this approach is simpler, it's also less flexible, since we can only work with one parameter selection at a time and can't view all parameters. The UDF `apply_func` also can't take keyword arguments, nor it can return anything other than outputs listed in `output_names`.
 
Note
 
If `apply_func` is a Numba-compiled function:
 
- All inputs are automatically converted to NumPy arrays 
- Each argument in `*args` must be of a Numba-compatible type 
- You cannot pass keyword arguments 
- Your outputs must be arrays of the same shape, data type and data order 
Args
 `apply_func` :&ensp;`callable` 
A function that takes inputs, selection of parameters, and other arguments, and does calculations to produce outputs.
 
Arguments are passed to `apply_func` in the following order:
 
- `input_shape` if `pass_input_shape` is set to True and `input_shape` not in `kwargs_to_args` 
- `col` if `per_column` and `pass_col` are set to True and `col` not in `kwargs_to_args` 
- broadcast time-series arrays corresponding to `input_names` 
- broadcast in-place output arrays corresponding to `in_output_names` 
- single parameter selection corresponding to `param_names` 
- variable arguments if `var_args` is set to True 
- arguments listed in `kwargs_to_args` 
- `flex_2d` if `pass_flex_2d` is set to True and `flex_2d` not in `kwargs_to_args` 
- keyword arguments if `apply_func` is not Numba-compiled 
Can be Numba-compiled.
 
Note
 
Shape of each output should be the same and match the shape of each input.
 `cache_func` :&ensp;`callable` 
A caching function to preprocess data beforehand.
 
Takes the same arguments as `apply_func`. Should return a single object or a tuple of objects. All returned objects will be passed unpacked as last arguments to `apply_func`.
 
Can be Numba-compiled.
 `pass_packed` :&ensp;`bool` Whether to pass packed tuples for inputs, in-place outputs, and parameters. `kwargs_to_args` :&ensp;`list` of `str` 
Keyword arguments from `kwargs` dict to pass as positional arguments to the apply function.
 
Should be used together with `numba_loop` set to True since Numba doesn't support variable keyword arguments.
 
Defaults to []. Order matters.
 `numba_loop` :&ensp;`bool` 
Whether to loop using Numba.
 
Set to True when iterating large number of times over small input, but note that Numba doesn't support variable keyword arguments.
 `pass_seed` :&ensp;`bool` Whether to pass `seed` to `apply_func` and `cache_func`. `**kwargs` Keyword arguments passed to IndicatorFactory.from_custom_func(). 
Returns
 
Indicator Additionally, each run method now supports `use_ray` argument, which indicates whether to use Ray to execute `apply_func` in parallel. Only works with `numba_loop` set to False. See ray_apply() for related keyword arguments.
 
Usage
 
- The following example produces the same indicator as the IndicatorFactory.from_custom_func() example. 
`>>> @njit
... def apply_func_nb(ts1, ts2, p1, p2, arg1, arg2):
... return ts1 * p1 + arg1, ts2 * p2 + arg2

>>> MyInd = vbt.IndicatorFactory(
... input_names=['ts1', 'ts2'],
... param_names=['p1', 'p2'],
... output_names=['o1', 'o2']
... ).from_apply_func(
... apply_func_nb, var_args=True,
... kwargs_to_args=['arg2'], arg2=200)

>>> myInd = MyInd.run(price, price * 2, [1, 2], [3, 4], 100)
>>> myInd.o1
custom_p1 1 2
custom_p2 3 4
 a b a b
2020-01-01 101.0 105.0 102.0 110.0
2020-01-02 102.0 104.0 104.0 108.0
2020-01-03 103.0 103.0 106.0 106.0
2020-01-04 104.0 102.0 108.0 104.0
2020-01-05 105.0 101.0 110.0 102.0
>>> myInd.o2
custom_p1 1 2
custom_p2 3 4
 a b a b
2020-01-01 206.0 230.0 208.0 240.0
2020-01-02 212.0 224.0 216.0 232.0
2020-01-03 218.0 218.0 224.0 224.0
2020-01-04 224.0 212.0 232.0 216.0
2020-01-05 230.0 206.0 240.0 208.0
` 
### from_custom_func method&para;
 
`IndicatorFactory.from_custom_func(
 custom_func,
 require_input_shape=False,
 param_settings=None,
 in_output_settings=None,
 hide_params=None,
 hide_default=True,
 var_args=False,
 keyword_only_args=False,
 **pipeline_kwargs
)
` 
Build indicator class around a custom calculation function.
 
In contrast to IndicatorFactory.from_apply_func(), this method offers full flexibility. It's up to we to handle caching and concatenate columns for each parameter (for example, by using apply_and_concat_one()). Also, you should ensure that each output array has an appropriate number of columns, which is the number of columns in input arrays multiplied by the number of parameter combinations.
 
Args
 `custom_func` :&ensp;`callable` 
A function that takes broadcast arrays corresponding to `input_names`, broadcast in-place output arrays corresponding to `in_output_names`, broadcast parameter arrays corresponding to `param_names`, and other arguments and keyword arguments, and returns outputs corresponding to `output_names` and other objects that are then returned with the indicator instance.
 
Can be Numba-compiled.
 
Note
 
Shape of each output should be the same and match the shape of each input stacked n times (= the number of parameter values) along the column axis.
 `require_input_shape` :&ensp;`bool` Whether to input shape is required. `param_settings` :&ensp;`dict` 
A dictionary of parameter settings keyed by name. See run_pipeline() for keys.
 
Can be overwritten by any run method.
 `in_output_settings` :&ensp;`dict` 
A dictionary of in-place output settings keyed by name. See run_pipeline() for keys.
 
Can be overwritten by any run method.
 `hide_params` :&ensp;`list` of `str` 
Parameter names to hide column levels for.
 
Can be overwritten by any run method.
 `hide_default` :&ensp;`bool` 
Whether to hide column levels of parameters with default value.
 
Can be overwritten by any run method.
 `var_args` :&ensp;`bool` 
Whether run methods should accept variable arguments (`*args`).
 
Set to True if `custom_func` accepts positional arguments that are not listed in the config.
 `keyword_only_args` :&ensp;`bool` 
Whether run methods should accept keyword-only arguments (`*`).
 
Set to True to force the user to use keyword arguments (e.g., to avoid misplacing arguments).
 `**pipeline_kwargs` 
Keyword arguments passed to run_pipeline().
 
Can be overwritten by any run method.
 
Can contain default values for `param_names` and `in_output_names`, but also custom positional and keyword arguments passed to the `custom_func`.
 
Returns
 
`Indicator`, and optionally other objects that are returned by `custom_func` and exceed `output_names`. Usage
 
- The following example produces the same indicator as the IndicatorFactory.from_apply_func() example. 
`>>> @njit
>>> def apply_func_nb(i, ts1, ts2, p1, p2, arg1, arg2):
... return ts1 * p1[i] + arg1, ts2 * p2[i] + arg2

>>> @njit
... def custom_func(ts1, ts2, p1, p2, arg1, arg2):
... return vbt.base.combine_fns.apply_and_concat_multiple_nb(
... len(p1), apply_func_nb, ts1, ts2, p1, p2, arg1, arg2)

>>> MyInd = vbt.IndicatorFactory(
... input_names=['ts1', 'ts2'],
... param_names=['p1', 'p2'],
... output_names=['o1', 'o2']
... ).from_custom_func(custom_func, var_args=True, arg2=200)

>>> myInd = MyInd.run(price, price * 2, [1, 2], [3, 4], 100)
>>> myInd.o1
custom_p1 1 2
custom_p2 3 4
 a b a b
2020-01-01 101.0 105.0 102.0 110.0
2020-01-02 102.0 104.0 104.0 108.0
2020-01-03 103.0 103.0 106.0 106.0
2020-01-04 104.0 102.0 108.0 104.0
2020-01-05 105.0 101.0 110.0 102.0
>>> myInd.o2
custom_p1 1 2
custom_p2 3 4
 a b a b
2020-01-01 206.0 230.0 208.0 240.0
2020-01-02 212.0 224.0 216.0 232.0
2020-01-03 218.0 218.0 224.0 224.0
2020-01-04 224.0 212.0 232.0 216.0
2020-01-05 230.0 206.0 240.0 208.0
` 
The difference between `apply_func_nb` here and in IndicatorFactory.from_apply_func() is that here it takes the index of the current parameter combination that can be used for parameter selection. You can also remove the entire `apply_func_nb` and define your logic in `custom_func` (which shouldn't necessarily be Numba-compiled):
 
`>>> @njit
... def custom_func(ts1, ts2, p1, p2, arg1, arg2):
... input_shape = ts1.shape
... n_params = len(p1)
... out1 = np.empty((input_shape[0], input_shape[1] * n_params), dtype=np.float64)
... out2 = np.empty((input_shape[0], input_shape[1] * n_params), dtype=np.float64)
... for k in range(n_params):
... for col in range(input_shape[1]):
... for i in range(input_shape[0]):
... out1[i, input_shape[1] * k + col] = ts1[i, col] * p1[k] + arg1
... out2[i, input_shape[1] * k + col] = ts2[i, col] * p2[k] + arg2
... return out1, out2
` 
### from_pandas_ta class method&para;
 
`IndicatorFactory.from_pandas_ta(
 func_name,
 parse_kwargs=None,
 init_kwargs=None,
 **kwargs
)
` 
Build an indicator class around a pandas-ta function.
 
Requires pandas-ta installed.
 
Args
 `func_name` :&ensp;`str` Function name. `parse_kwargs` :&ensp;`dict` Keyword arguments passed to IndicatorFactory.parse_pandas_ta_config(). `init_kwargs` :&ensp;`dict` Keyword arguments passed to IndicatorFactory. `**kwargs` Keyword arguments passed to IndicatorFactory.from_custom_func(). 
Returns
 
Indicator Usage
 
`>>> SMA = vbt.IndicatorFactory.from_pandas_ta('SMA')

>>> sma = SMA.run(price, length=[2, 3])
>>> sma.sma
sma_length 2 3
 a b a b
2020-01-01 NaN NaN NaN NaN
2020-01-02 1.5 4.5 NaN NaN
2020-01-03 2.5 3.5 2.0 4.0
2020-01-04 3.5 2.5 3.0 3.0
2020-01-05 4.5 1.5 4.0 2.0
` 
- To get help on running the indicator, use the `help` command: 
`>>> help(SMA.run)
Help on method run:

run(close, length=None, offset=None, short_name='sma', hide_params=None, hide_default=True, **kwargs) method of builtins.type instance
 Run `SMA` indicator.

 * Inputs: `close`
 * Parameters: `length`, `offset`
 * Outputs: `sma`

 Pass a list of parameter names as `hide_params` to hide their column levels.
 Set `hide_default` to False to show the column levels of the parameters with a default value.

 Other keyword arguments are passed to [run_pipeline()](/api/indicators/factory/#vectorbt.indicators.factory.run_pipeline "vectorbt.indicators.factory.run_pipeline").
` 
- To get the indicator docstring, use the `help` command or print the `__doc__` attribute: 
`>>> print(SMA.__doc__)
Simple Moving Average (SMA)

The Simple Moving Average is the classic moving average that is the equally
weighted average over n periods.

Sources:
 <https://www.tradingtechnologies.com/help/x-study/technical-indicator-definitions/simple-moving-average-sma/>

Calculation:
 Default Inputs:
 length=10
 SMA = SUM(close, length) / length

Args:
 close (pd.Series): Series of 'close's
 length (int): It's period. Default: 10
 offset (int): How many periods to offset the result. Default: 0

Kwargs:
 adjust (bool): Default: True
 presma (bool, optional): If True, uses SMA for initial value.
 fillna (value, optional): pd.DataFrame.fillna(value)
 fill_method (value, optional): Type of fill method

Returns:
 pd.Series: New feature generated.
` 
### from_ta class method&para;
 
`IndicatorFactory.from_ta(
 cls_name,
 init_kwargs=None,
 **kwargs
)
` 
Build an indicator class around a ta class.
 
Requires ta installed.
 
Args
 `cls_name` :&ensp;`str` Class name. `init_kwargs` :&ensp;`dict` Keyword arguments passed to IndicatorFactory. `**kwargs` Keyword arguments passed to IndicatorFactory.from_custom_func(). 
Returns
 
Indicator Usage
 
`>>> SMAIndicator = vbt.IndicatorFactory.from_ta('SMAIndicator')

>>> sma = SMAIndicator.run(price, window=[2, 3])
>>> sma.sma_indicator
smaindicator_window 2 3
 a b a b
2020-01-01 NaN NaN NaN NaN
2020-01-02 1.5 4.5 NaN NaN
2020-01-03 2.5 3.5 2.0 4.0
2020-01-04 3.5 2.5 3.0 3.0
2020-01-05 4.5 1.5 4.0 2.0
` 
- To get help on running the indicator, use the `help` command: 
`>>> help(SMAIndicator.run)
Help on method run:

run(close, window, fillna=False, short_name='smaindicator', hide_params=None, hide_default=True, **kwargs) method of builtins.type instance
 Run `SMAIndicator` indicator.

 * Inputs: `close`
 * Parameters: `window`, `fillna`
 * Outputs: `sma_indicator`

 Pass a list of parameter names as `hide_params` to hide their column levels.
 Set `hide_default` to False to show the column levels of the parameters with a default value.

 Other keyword arguments are passed to [run_pipeline()](/api/indicators/factory/#vectorbt.indicators.factory.run_pipeline "vectorbt.indicators.factory.run_pipeline").
` 
- To get the indicator docstring, use the `help` command or print the `__doc__` attribute: 
`>>> print(SMAIndicator.__doc__)
SMA - Simple Moving Average

 Args:
 close(pandas.Series): dataset 'Close' column.
 window(int): n period.
 fillna(bool): if True, fill nan values.
` 
### from_talib class method&para;
 
`IndicatorFactory.from_talib(
 func_name,
 init_kwargs=None,
 **kwargs
)
` 
Build an indicator class around a TA-Lib function.
 
Requires TA-Lib installed.
 
For input, parameter and output names, see docs.
 
Args
 `func_name` :&ensp;`str` Function name. `init_kwargs` :&ensp;`dict` Keyword arguments passed to IndicatorFactory. `**kwargs` Keyword arguments passed to IndicatorFactory.from_custom_func(). 
Returns
 
Indicator Usage
 
`>>> SMA = vbt.IndicatorFactory.from_talib('SMA')

>>> sma = SMA.run(price, timeperiod=[2, 3])
>>> sma.real
sma_timeperiod 2 3
 a b a b
2020-01-01 NaN NaN NaN NaN
2020-01-02 1.5 4.5 NaN NaN
2020-01-03 2.5 3.5 2.0 4.0
2020-01-04 3.5 2.5 3.0 3.0
2020-01-05 4.5 1.5 4.0 2.0
` 
- To get help on running the indicator, use the `help` command: 
`>>> help(SMA.run)
Help on method run:

run(close, timeperiod=30, short_name='sma', hide_params=None, hide_default=True, **kwargs) method of builtins.type instance
 Run `SMA` indicator.

 * Inputs: `close`
 * Parameters: `timeperiod`
 * Outputs: `real`

 Pass a list of parameter names as `hide_params` to hide their column levels.
 Set `hide_default` to False to show the column levels of the parameters with a default value.

 Other keyword arguments are passed to [run_pipeline()](/api/indicators/factory/#vectorbt.indicators.factory.run_pipeline "vectorbt.indicators.factory.run_pipeline").
` 
### get_pandas_ta_indicators class method&para;
 
`IndicatorFactory.get_pandas_ta_indicators(
 silence_warnings=True
)
` 
Get all pandas-ta indicators.
 
Note
 
Returns only the indicators that have been successfully parsed.
 
### get_ta_indicators class method&para;
 
`IndicatorFactory.get_ta_indicators()
` 
Get all ta indicators.
 
### get_talib_indicators class method&para;
 
`IndicatorFactory.get_talib_indicators()
` 
Get all TA-Lib indicators.
 
### parse_pandas_ta_config class method&para;
 
`IndicatorFactory.parse_pandas_ta_config(
 func,
 test_input_names=None,
 test_index_len=100
)
` 
Get the config of a pandas-ta indicator.
 
### parse_ta_config class method&para;
 
`IndicatorFactory.parse_ta_config(
 ind_cls
)
` 
Get the config of a ta indicator.
 
## MetaIndicatorBase class&para;
 
`MetaIndicatorBase(
 *args,
 **kwargs
)
` 
Meta class that exposes a read-only class property `StatsBuilderMixin.metrics`.
 
Superclasses
 
- MetaPlotsBuilderMixin 
- MetaStatsBuilderMixin 
- `builtins.type` 
Inherited members
 
- MetaPlotsBuilderMixin.subplots 
- MetaStatsBuilderMixin.metrics 
 Back to top