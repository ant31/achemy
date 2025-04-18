# Aiochemy Documentation

Aiochemy is a Python library that simplifies database interactions by providing an Active Record pattern and automatic session management. It supports both synchronous and asynchronous operations, making it flexible for various application needs. 

## Installation

```bash
pip install aiochemy
```

## Configuration

Aiochemy uses a configuration schema to manage database connection details. Here's an example using the `PostgreSQLConfigSchema`:

```python
from aiochemy.config import PostgreSQLConfigSchema

config = PostgreSQLConfigSchema(
    db="mydatabase",
    user="myuser",
    password="mypassword",
    host="localhost",
    port=5432,
)
```
See `mise.local.toml` and other examples for different configuration options.

## Setting up the Engine

The `ActiveEngine` class manages database connections.  You can set it up for synchronous or asynchronous operations:

**Synchronous:**

```python
from aiochemy import ActiveEngine

engine = ActiveEngine(config)
```

**Asynchronous:**

```python
from aiochemy.aio import ActiveEngine

engine = ActiveEngine(config)
```

Set the engine for your models:

```python
from aiochemy import ActiveRecord
from myapp.models import MyModel # Assuming 'MyModel' inherits from ActiveRecord

MyModel.set_engine(engine)
```

## Basic CRUD Operations

### Creating and Saving Records

```python
from myapp.models import User

# Method 1: Create and save.
user = User(name="Alice", email="alice@example.com")
user.save()

# Method 2: Using add.
user = User(name="Bob")
User.add(user, commit=True) # commit=True commits the change immediately.
```

### Querying

```python
# Retrieve all users
users = User.all()

# Find a user by primary key.
user_pk = uuid.UUID("some uuid here")
user = User.find(user_pk) # using PKMixin which adds find().


# Find a user by email
user = User.find_by(email="alice@example.com")

# Find users with a specific name
users = User.where(User.name == "Alice").all()


# Find the first user in the database.
first_user = User.first() # Orders by the primary key.


# Find the last user in the database, ordered by a column.
last_user = User.last(User.name) # Orders by User.name DESC.


# Use a custom query with advanced selects
query = User.select().where(User.created_at < some_date)
users = User.all(query=query) # Can combine custom queries with other operations

# Find the first created user
first_created_user = User.first_created()

# Find the last created user
last_created_user = User.last_created()

# Count users
user_count = User.count()


```

### Updating Records

```python
user = User.find_by(name="Alice")
if user:
    user.name = "Alicia"
    user.save()
```

### Deleting Records
```python
user = User.find_by(name="Bob")
if user:
    User.delete(user)
```


### Asynchronous Operations

Aiochemy supports asynchronous operations using `asyncio` and `async/await`. Use `aiochemy.aio.ActiveRecord`, `aiochemy.aio.ActiveEngine`, and `aiochemy.aio.Schema`:

```python
import asyncio
from aiochemy.aio import ActiveRecord, Schema

# ... (setup engine as described above, using the async ActiveEngine) ...

async def create_user():
    user = User(name="Dave")
    await user.save()
    print(f"Created user: {user}")

asyncio.run(create_user())

# Use async methods for querying and operations
users = await User.all()

# Convert model instances to dictionaries and vice-versa
user_data = user.dump_model()
restored_user = User.load(**user_data)

schema = User.Schema() # Convert schemas to model instances and back
user_instance = schema.to_model(User)
user_schema = User.Schema.model_validate(user_instance)
```
See `aiochemy/demo/amodels.py` for a detailed example.

### Explicit sessions

```python
session = User.new_session()
try:
    user = User(name='Bob')
    session.add(user)
    session.commit()
finally:
    session.close()

# async
async def async_example():
    async_session = await User.new_session()
    try:
        user = User(name='Bob')
        async_session.add(user)
        await async_session.commit()
    finally:
        await async_session.close()

async def context_session():
    async with User.new_session() as session:    
        user = User(name='Bob')        
        async_session.add(user)
        await async_session.commit(session)
        # or 
        user2 = User(name='Alice')
        user2 = await Use.add(user2, commit=True, session=session)
```
 

### Transactions

Transactions are automatically handled for `add()`, `delete()`, and `save()`.

For fine-grained control use a context manager with `begin()` and `begin_nested()`:
```python

with User.new_session() as session
    try:
        # Operations here
        # Rollback will happen automatically
        session.add(user1)
        session.add(user2)
        1 / 0 # Will rollback to here
    except Exception as e:
        print(f"Error: {e}") # Will rollback to here
    session.commit()
    
## Session is closed on context exit
```
See `aiochemy/utils/retry.py` for how the Q context manager implements retries and transactions.



### Custom Schemas

Create custom schemas by inheriting from `aiochemy.Schema` or `aiochemy.aio.Schema` and using Pydantic's features.


## Examples

For more comprehensive examples, refer to the following:

* `aiochemy/demo` for sample models and usage.
* `models.py` and `amodels.py` for synchronous and asynchronous model definitions.



This documentation provides a starting point for using Aiochemy. Explore the code examples and docstrings for more in-depth information.
