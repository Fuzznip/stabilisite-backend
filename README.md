# stability-prototypes

## Database Setup
First you will need to create a `.env` file with the following information to connect to your postgres database:
```commandline
DATABASE_USERNAME
DATABASE_PASSWORD
DATABASE_URL
```
Once your `.env` file is created, you can run the following commands to generate the ables in your database:
```commandline
flask db init
flask db migrate
flask db upgrade
```

## Flask setup
Once you have the database setup correctly, you will need to set the FLASK_APP environment variable:
```
EXPORT FLASK_APP=app.py
```

Once that has been set, you can start the app with:
```commandline
flask run
```

or with a WSGI server:
```commandline
waitress-serve --host=0.0.0.0 --port=5000 app:app
```


## Trial coordination

Optional backend-owned trial board: [setup, API and tests](docs/trial-board.md).
Paired with Stabilibot PR #29. Disabled by default; requires a database migration.
