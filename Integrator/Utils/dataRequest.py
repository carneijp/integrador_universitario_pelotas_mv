import sqlalchemy as sa
import pandas as pd
from Utils import Constant as C

# Real Batching: https://pythonspeed.com/articles/pandas-sql-chunking/
def get_data(queryText:str):
    query = sa.text(queryText)
    df = pd.read_sql(query, C.DATABASE_SOURCE, index_col= None)
    return df

# o comando _execute_ deve permitir a execução de comandos em uma database PostgreSQL, 
#  como por exemplo a criação de INDEX para as tabelas
# https://docs.sqlalchemy.org/en/20/core/connections.html
def execute(queryText:str, payload: dict):
    with C.DATABASE_SOURCE.connect() as connection:
            connection.execute(sa.text(queryText), payload)
            connection.commit()
