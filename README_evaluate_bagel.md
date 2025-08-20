# BAGEL City: Evaluating and Loading Results

This guide assumes you have already generated results as described in [README_run_bagel.md](README_run_bagel.md).

The evaluation and database loading workflow supports both SQLite and PostgreSQL databases. You can use the provided scripts to create the necessary files and load them into your database of choice.

## 1. Create Evaluation Database Files

Use the following script to generate the files needed for database loading:

```
python scripts/create_evaluation_database_files.py --run RUN_NAME
```
- `--run RUN_NAME` specifies the run directory (e.g., `run_1`).
- This will create the necessary TSV/CSV files in the corresponding `data/RUN_NAME/` directory.

## 2. Load Results into a Database

You can load the results into either a SQLite or PostgreSQL database using the following scripts:

### For SQLite:

```
python scripts/load_sqlite.py --run RUN_NAME
```
- This will load the evaluation files into a SQLite database (e.g., `data/RUN_NAME/evaluation.db`).

### For PostgreSQL:

```
python scripts/load_postgres.py --run RUN_NAME --host HOST --user USER --password PASSWORD --dbname DBNAME
```
- Replace the connection arguments with your PostgreSQL credentials and database name.

## 3. Updating an Existing Database

Both `load_sqlite.py` and `load_postgres.py` support an `--update` argument. Use this flag to update an existing database with new or changed results, rather than recreating the database from scratch.

**Example:**

```
python scripts/load_sqlite.py --run run_1 --update
```

or

```
python scripts/load_postgres.py --run run_1 --update --host ... --user ... --password ... --dbname ...
```

This will update the relevant tables in the database with any new or modified data from the evaluation files.

## 4. Running the Evaluation Web App

After loading your results into a database, you can use the evaluation web app to assess and analyze the results. The app supports both SQLite and PostgreSQL backends, selected via environment variables.

### For SQLite

Set the environment variable `SQLITE_DB_PATH` to the path of your SQLite database file, then run the app:

```
export SQLITE_DB_PATH=/full/path/to/data/RUN_NAME/evaluation.db
python evaluation_app/evaluate.py --model MODEL_NAME
```
- Replace `MODEL_NAME` with the model you want to view in the browser.

### For PostgreSQL

Set the following environment variables, then run the app:

```
export DB_BACKEND=postgres
export DB_HOST=your_host
export DB_PORT=5432
export DB_NAME=your_db
export DB_USER=your_user
export DB_PASSWORD=your_password
python evaluation_app/evaluate.py --model MODEL_NAME
```
- Replace the values with your PostgreSQL credentials and database name.
- Replace `MODEL_NAME` with the model you want to view in the browser.

### Accessing the App

Once the app is running, open your browser and go to [http://localhost:5000/](http://localhost:5000/) to use the evaluation interface.

---

For more details on script options, use the `--help` flag:

```
python evaluation_app/evaluate.py --help
```
