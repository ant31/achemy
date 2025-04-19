# Achemy Documentation

Achemy is an asynchronous Python library that simplifies database interactions by providing an Active Record pattern implementation built on SQLAlchemy 2.0+. It focuses on async operations and automatic session management for ease of use.

## Installation

```bash
pip install achemy
```

## Configuration

Achemy uses a configuration schema to manage database connection details. Here's an example using the `PostgreSQLConfigSchema`:

```python
from achemy.config import PostgreSQLConfigSchema

config = PostgreSQLConfigSchema(
    db="mydatabase",
    user="myuser",
    password="mypassword",
    host="localhost",
    port=5432,
    # driver="asyncpg" # Default is asyncpg
)
```
See `achemy/config.py` and `tests/test_config.py` for more configuration options.

## Setting up the Engine

The `ActiveEngine` class manages asynchronous database connections. Initialize it with your configuration:

```python
from achemy import ActiveEngine, ActiveRecord
from achemy.demo.amodels import ACountry # Example model

# Create the engine instance
engine = ActiveEngine(config)

# Set the engine globally for all ActiveRecord models
# or set it specifically for base classes or individual models
ActiveRecord.set_engine(engine)
# Alternatively: ACountry.set_engine(engine)
```

## Basic CRUD Operations

### Creating and Saving Records

```python
from myapp.models import User

# Method 1: Create and save.
# 'commit=True' (default is False) will commit the session automatically.
# If commit=False, the object is added to the session and flushed (to get ID),
# but requires an explicit session.commit() later.
user = User(name="Alice", email="alice@example.com")
await user.save(commit=True) # Use await for async operations

# Method 2: Using the class method 'add'.
user_bob = User(name="Bob")
await User.add(user_bob, commit=True) # commit=True commits the change immediately.

# Add multiple records efficiently
users_to_add = [
    User(name="Charlie"),
    User(name="Diana")
]
await User.add_all(users_to_add, commit=True)
```

### Querying

```python
# Retrieve all users (potentially many, use with caution or filtering)
all_users = await User.all()

# Get a user by primary key (optimized)
user_pk = uuid.UUID("some uuid here")
user_by_pk = await User.get(user_pk)

# Find a user by primary key using the PKMixin helper 'find'
# (This is equivalent to User.get(user_pk) if PKMixin is used)
user_by_find = await User.find(user_pk)

# Find the first user matching specific criteria
user_by_email = await User.find_by(email="alice@example.com")

# Find all users matching specific criteria
users_named_alice = await User.all(query=User.where(User.name == "Alice"))
# Or directly using where() which returns a Select object
select_query = User.where(User.name == "Alice")
# Execute the query using .all() or .first() etc.
users_named_alice_alt = await User.all(query=select_query)


# Find the first user overall (default order by primary key).
first_user = await User.first()

# Find the first user ordered by a specific column (e.g., name ascending)
first_user_by_name = await User.first(order_by=User.name.asc())

# Find the most recently created user (requires UpdateMixin)
latest_user = await User.last_created()

# Find the oldest user (requires UpdateMixin)
oldest_user = await User.first_created()

# Find the most recently updated user (requires UpdateMixin)
last_updated_user = await User.last_modified()

# Get users modified since a specific datetime (requires UpdateMixin)
from datetime import datetime, timedelta
one_day_ago = datetime.utcnow() - timedelta(days=1)
recent_users = await User.get_since(one_day_ago)

# Use a custom query with advanced selects
# Note: .select() creates the query object, execution methods like .all() run it.
query = User.select().where(User.created_at < some_date).order_by(User.name.desc())
selected_users = await User.all(query=query)

# Count users matching criteria
active_user_count = await User.count(query=User.where(User.is_active == True))

# Count all users
total_user_count = await User.count()


```

### Updating Records

```python
user = await User.find_by(name="Alice")
if user:
    user.name = "Alicia"
    await user.save(commit=True) # Remember await and commit=True
```

### Deleting Records
```python
user = await User.find_by(name="Bob")
if user:
    await User.delete(user, commit=True) # Remember await and commit=True
```

### Data Handling and Schemas

Achemy models provide methods for data conversion:

```python
user = await User.find_by(name="Alicia")

# Convert model instance to a dictionary (mapped columns only)
user_dict = user.to_dict()
print(user_dict)
# Output: {'id': UUID('...'), 'name': 'Alicia', 'email': '...', ...}

# Convert to a JSON-serializable dictionary (handles UUID, datetime, etc.)
user_json_serializable = user.dump_model()
print(user_json_serializable)
# Output: {'id': '...', 'name': 'Alicia', 'email': '...', ...}

# Load data from a dictionary into a new model instance
# Note: Only sets attributes corresponding to mapped columns.
new_user_data = {"name": "Eve", "email": "eve@example.com", "extra_field": "ignored"}
new_user_instance = User.load(new_user_data)
print(new_user_instance.name) # Output: Eve
# print(new_user_instance.id) # Output: None (unless 'id' was in the dict)

# Using Pydantic Schemas (Optional)
# Define a Pydantic schema for your model
from achemy import Schema as BaseSchema

class UserSchema(BaseSchema[User]): # Generic type hint to User model
    name: str
    email: str | None = None
    # Add other fields as needed, matching model attributes

# Create schema from model instance
user_schema_instance = UserSchema.model_validate(user)
print(user_schema_instance.model_dump())

# Create model instance from schema instance
model_from_schema = user_schema_instance.to_model(User)
print(model_from_schema.name)
```
See `achemy/schema.py` and `tests/test_schema.py` for more details.

### Explicit Session Management

While Achemy methods often handle sessions internally (creating one if needed), you can manage sessions explicitly for more control, especially for transactions spanning multiple operations.

Use `Model.get_session()` with an `async with` block:

```python
async def complex_operation():
    # get_session() provides a session managed by the context manager
    async with await User.get_session() as session:
        try:
            user_frank = User(name='Frank')
            # Pass the explicit session to ActiveRecord methods
            await User.add(user_frank, commit=False, session=session) # commit=False within transaction

            # Perform other operations with the same session
            city = City(name="Frankfurt")
            await city.save(commit=False, session=session)

            # Commit the transaction explicitly at the end
            await session.commit()
            print("Transaction committed successfully.")

        except Exception as e:
            print(f"An error occurred: {e}. Rolling back transaction.")
            # Rollback happens automatically when exiting 'async with' on error
            # await session.rollback() # Explicit rollback is usually not needed here
```
### Transactions

When using explicit session management with `async with await Model.get_session() as session:`, the session context manager automatically handles transactions:
*   If the block completes successfully, the transaction is committed (if `session.commit()` was called).
*   If an exception occurs within the block, the transaction is automatically rolled back.

Example:
```python
async def transaction_example():
    async with await User.get_session() as session:
        try:
            user1 = User(name="TxUser1")
            await session.add(user1) # Add to session, no commit yet

            user2 = User(name="TxUser2")
            await session.add(user2)

            # Simulate an error before commit
            if some_condition:
                 raise ValueError("Something went wrong!")

            # If no error, commit the changes
            await session.commit()
            print("Users added successfully.")

        except ValueError as e:
            print(f"Transaction failed and rolled back: {e}")
            # Rollback is automatic here
        # Session is closed automatically upon exiting the 'async with' block
```

### Mixins

Achemy provides helpful mixins:

*   **`PKMixin`**: Adds a standard `id: Mapped[uuid.UUID]` primary key column with a default UUID factory and `server_default`. Also adds the `find(pk_uuid)` classmethod as a convenient alias for `get(pk_uuid)`.
*   **`UpdateMixin`**: Adds `created_at: Mapped[datetime]` and `updated_at: Mapped[datetime]` timestamp columns with automatic `server_default` and `onupdate` behavior. Provides classmethods like `last_created()`, `first_created()`, `last_modified()`, and `get_since(datetime)`.

```python
from achemy import Base, PKMixin, UpdateMixin
from sqlalchemy.orm import Mapped, mapped_column

class MyModel(Base, PKMixin, UpdateMixin):
    __tablename__ = "my_models"
    name: Mapped[str] = mapped_column()

# Now MyModel has id, created_at, updated_at columns and related methods.
latest = await MyModel.last_modified()
instance = await MyModel.find(some_uuid)
```

## Examples

For more comprehensive examples, refer to the following:

*   `achemy/demo/amodels.py`: Sample asynchronous model definitions demonstrating relationships and usage.
*   `tests/`: Contains various unit and integration tests showcasing different features.

This documentation provides a starting point for using Achemy. Explore the code examples, tests, and docstrings for more in-depth information.
