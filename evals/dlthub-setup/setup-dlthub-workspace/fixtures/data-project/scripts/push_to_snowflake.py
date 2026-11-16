"""Upload data/orders.csv to the RAW.SHOPIFY.ORDERS table in Snowflake."""

import os

import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

conn = snowflake.connector.connect(
    account=os.environ["SF_ACCOUNT"],
    user=os.environ["SF_USER"],
    password=os.environ["SF_PASSWORD"],
    warehouse="LOAD_WH",
    database="RAW",
    schema="SHOPIFY",
)
write_pandas(conn, pd.read_csv("data/orders.csv"), "ORDERS", auto_create_table=True, overwrite=True)
