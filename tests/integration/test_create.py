import dask.dataframe as dd
import pandas as pd
import pytest

import dask_sql
from tests.utils import assert_eq


@pytest.mark.parametrize("gpu", [False, pytest.param(True, marks=pytest.mark.gpu)])
def test_create_from_csv(c, df, temporary_data_file, gpu):
    df.to_csv(temporary_data_file, index=False)

    c.sql(
        f"""
        CREATE TABLE
            new_table
        WITH (
            location = '{temporary_data_file}',
            format = 'csv',
            gpu = {gpu}
        )
    """
    )

    result_df = c.sql(
        """
        SELECT * FROM new_table
    """
    )

    assert_eq(result_df, df)


@pytest.mark.parametrize(
    "gpu",
    [
        False,
        pytest.param(True, marks=pytest.mark.gpu),
    ],
)
def test_cluster_memory(client, c, df, gpu):
    client.publish_dataset(df=dd.from_pandas(df, npartitions=1))

    c.sql(
        f"""
        CREATE TABLE
            new_table
        WITH (
            location = 'df',
            format = 'memory',
            gpu = {gpu}
        )
    """
    )

    return_df = c.sql(
        """
        SELECT * FROM new_table
    """
    )

    assert_eq(df, return_df)

    client.unpublish_dataset("df")


@pytest.mark.parametrize("gpu", [False, pytest.param(True, marks=pytest.mark.gpu)])
def test_create_from_csv_persist(c, df, temporary_data_file, gpu):
    df.to_csv(temporary_data_file, index=False)

    c.sql(
        f"""
        CREATE TABLE
            new_table
        WITH (
            location = '{temporary_data_file}',
            format = 'csv',
            persist = True,
            gpu = {gpu}
        )
    """
    )

    return_df = c.sql(
        """
        SELECT * FROM new_table
    """
    )

    assert_eq(df, return_df)


def test_wrong_create(c):
    with pytest.raises(AttributeError):
        c.sql(
            """
            CREATE TABLE
                new_table
            WITH (
                format = 'csv'
            )
        """
        )

    with pytest.raises(AttributeError):
        c.sql(
            """
            CREATE TABLE
                new_table
            WITH (
                format = 'strange',
                location = 'some/path'
            )
        """
        )


def test_create_from_query(c, df):
    c.sql(
        """
        CREATE OR REPLACE TABLE
            new_table
        AS (
            SELECT * FROM df
        )
    """
    )

    return_df = c.sql(
        """
        SELECT * FROM new_table
    """
    )

    assert_eq(df, return_df)

    c.sql(
        """
        CREATE OR REPLACE VIEW
            new_table
        AS (
            SELECT * FROM df
        )
    """
    )

    return_df = c.sql(
        """
        SELECT * FROM new_table
    """
    )

    assert_eq(df, return_df)


@pytest.mark.parametrize(
    "gpu",
    [
        False,
        pytest.param(
            True,
            marks=pytest.mark.gpu,
        ),
    ],
)
def test_view_table_persist(c, temporary_data_file, df, gpu):
    df.to_csv(temporary_data_file, index=False)
    c.sql(
        f"""
        CREATE TABLE
            new_table
        WITH (
            location = '{temporary_data_file}',
            format = 'csv',
            gpu = {gpu}
        )
    """
    )

    # Views should change, when the original data changes
    # Tables should not change, when the original data changes
    c.sql(
        """
        CREATE VIEW
            count_view
        AS (
            SELECT COUNT(*) AS c FROM new_table
        )
    """
    )
    c.sql(
        """
        CREATE TABLE
            count_table
        AS (
            SELECT COUNT(*) AS c FROM new_table
        )
    """
    )

    from_view = c.sql("SELECT c FROM count_view")
    from_table = c.sql("SELECT c FROM count_table")

    assert_eq(from_view, pd.DataFrame({"c": [700]}))
    assert_eq(from_table, pd.DataFrame({"c": [700]}))

    df.iloc[:10].to_csv(temporary_data_file, index=False)

    from_view = c.sql("SELECT c FROM count_view")
    from_table = c.sql("SELECT c FROM count_table")

    assert_eq(from_view, pd.DataFrame({"c": [10]}))
    assert_eq(from_table, pd.DataFrame({"c": [700]}))


def test_replace_and_error(c, temporary_data_file, df):
    c.sql(
        """
        CREATE TABLE
            new_table
        AS (
            SELECT 1 AS a
        )
    """
    )

    assert_eq(
        c.sql("SELECT a FROM new_table"),
        pd.DataFrame({"a": [1]}),
        check_dtype=False,
    )

    with pytest.raises(RuntimeError):
        c.sql(
            """
            CREATE TABLE
                new_table
            AS (
                SELECT 1
            )
        """
        )

    c.sql(
        """
        CREATE TABLE IF NOT EXISTS
            new_table
        AS (
            SELECT 2 AS a
        )
    """
    )

    assert_eq(
        c.sql("SELECT a FROM new_table"),
        pd.DataFrame({"a": [1]}),
        check_dtype=False,
    )

    c.sql(
        """
        CREATE OR REPLACE TABLE
            new_table
        AS (
            SELECT 2 AS a
        )
    """
    )

    assert_eq(
        c.sql("SELECT a FROM new_table"),
        pd.DataFrame({"a": [2]}),
        check_dtype=False,
    )

    c.sql("DROP TABLE new_table")

    with pytest.raises(dask_sql.utils.ParsingException):
        c.sql("SELECT a FROM new_table")

    c.sql(
        """
        CREATE TABLE IF NOT EXISTS
            new_table
        AS (
            SELECT 3 AS a
        )
    """
    )

    assert_eq(
        c.sql("SELECT a FROM new_table"),
        pd.DataFrame({"a": [3]}),
        check_dtype=False,
    )

    df.to_csv(temporary_data_file, index=False)
    with pytest.raises(RuntimeError):
        c.sql(
            f"""
            CREATE TABLE
                new_table
            WITH (
                location = '{temporary_data_file}',
                format = 'csv'
            )
        """
        )

    c.sql(
        f"""
        CREATE TABLE IF NOT EXISTS
            new_table
        WITH (
            location = '{temporary_data_file}',
            format = 'csv'
        )
    """
    )

    assert_eq(
        c.sql("SELECT a FROM new_table"),
        pd.DataFrame({"a": [3]}),
        check_dtype=False,
    )

    c.sql(
        f"""
        CREATE OR REPLACE TABLE
            new_table
        WITH (
            location = '{temporary_data_file}',
            format = 'csv'
        )
    """
    )

    result_df = c.sql("SELECT * FROM new_table")

    assert_eq(result_df, df)


def test_drop(c):
    with pytest.raises(RuntimeError):
        c.sql("DROP TABLE new_table")

    c.sql("DROP TABLE IF EXISTS new_table")

    c.sql(
        """
        CREATE TABLE
            new_table
        AS (
            SELECT 1 AS a
        )
    """
    )

    c.sql("DROP TABLE IF EXISTS new_table")

    with pytest.raises(dask_sql.utils.ParsingException):
        c.sql("SELECT a FROM new_table")


def test_create_gpu_error(c, df, temporary_data_file):
    try:
        import cudf
    except ImportError:
        cudf = None

    if cudf is not None:
        pytest.skip("GPU-related import errors only need to be checked on CPU")

    with pytest.raises(ModuleNotFoundError):
        c.create_table("new_table", df, gpu=True)

    with pytest.raises(ModuleNotFoundError):
        c.create_table("new_table", dd.from_pandas(df, npartitions=2), gpu=True)

    df.to_csv(temporary_data_file, index=False)

    with pytest.raises(ModuleNotFoundError):
        c.sql(
            f"""
            CREATE TABLE
                new_table
            WITH (
                location = '{temporary_data_file}',
                format = 'csv',
                gpu = True
            )
        """
        )
