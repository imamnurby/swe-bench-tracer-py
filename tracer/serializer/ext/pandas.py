def register_handlers():
    try:
        import pandas as pd
        from jsonpickle.ext import pandas as jsonpickle_pandas
        jsonpickle_pandas.register_handlers()
        return [
            pd.DataFrame, pd.Series, pd.Index, pd.PeriodIndex,
            pd.MultiIndex, pd.Timestamp, pd.Period, pd.Interval,
        ]
    except ImportError:
        return []