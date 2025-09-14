# Achemy Documentation

Achemy is an asynchronous Python library that simplifies database interactions by providing an Active Record pattern implementation built on SQLAlchemy 2.0+. It focuses on async operations, automatic session management, and seamless Pydantic integration for ease of use.

## Features

-   **Active Record Pattern**: Intuitive, model-centric methods for database operations (`User.all()`, `user.save()`).
-   **Async First**: Built for modern asynchronous applications with `async/await`.
-   **Automatic Session Management**: Achemy handles session creation and cleanup, reducing boilerplate code.
-   **Pydantic Integration**: Automatically generate Pydantic schemas from your SQLAlchemy models for API validation and serialization.
-   **Bulk Operations**: Efficiently insert large numbers of records with support for conflict resolution.
-   **Helpful Mixins**: Common patterns like UUID primary keys and timestamp tracking are available as simple mixins.

## Installation

```bash
pip install achemy
```

## Getting Started: A Complete Example

Let's build a simple application to manage users.

### Step 1: Configuration

Achemy uses a Pydantic schema to manage database connection details.

```python
# config.py
from achemy.config import PostgreSQLConfigSchema

db_config = PostgreSQLConfigSchema(
    db="mydatabase",
    user="myuser",
    password="mypassword",
    host="localhost",
    port=5432,
)
```
See `achemy/config.py` for more options.

### Step 2: Engine and Model Setup

Initialize the `ActiveEngine` and define your models. It's good practice to create a common base class for your models.

```python
# models.py
from sqlalchemy.orm import Mapped, mapped_column

from achemy import Base, PKMixin, UpdateMixin


# It's recommended to create your own Base class for your models
class AppBase(Base):
    __abstract__ = True
    # You can add shared logic or configurations here


class User(AppBase, PKMixin, UpdateMixin):
    """A user model with UUID primary key and timestamps."""

    __tablename__ = "users"

    name: Mapped[str] = mapped_column()
    email: Mapped[str] = mapped_column(unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
```

### Step 3: Initialize the Engine

In your application's entry point, create the engine and link it to your models.

```python
# main.py
import asyncio

from achemy import ActiveEngine, ActiveRecord

from config import db_config
from models import User

# Create the engine instance
engine = ActiveEngine(db_config)

# Set the engine globally for all ActiveRecord models
ActiveRecord.set_engine(engine)


async def main():
    # Your application logic here
    # Example: create a user
    new_user = User(name="Alice", email="alice@example.com")
    await new_user.save(commit=True)
    print(f"Created user: {new_user}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Basic CRUD Operations

### Creating and Saving Records

```python
# Method 1: Create an instance and save it.
# `commit=True` will commit the session automatically.
user = User(name="Alice", email="alice@example.com")
await user.save(commit=True)

# Method 2: Use the class method 'add'.
user_bob = User(name="Bob", email="bob@example.com")
await User.add(user_bob, commit=True)

# Add multiple records at once
users_to_add = [User(name="Charlie", email="charlie@example.com"), User(name="Diana", email="diana@example.com")]
await User.add_all(users_to_add, commit=True)
```
If `commit=False`, the object is added to the session and flushed (to get the ID), but requires an explicit `session.commit()` later.

### Querying Records

```python
# Get all users (use with caution on large tables)
all_users = await User.all()

# Get a user by primary key (highly optimized)
user_by_pk = await User.get(some_uuid)

# Find a user by primary key using the PKMixin helper 'find'
# (This is equivalent to User.get(pk))
user_by_find = await User.find(some_uuid)

# Find the first user matching specific criteria
user_by_email = await User.find_by(email="alice@example.com")

# Find all users matching criteria
active_users = await User.all(query=User.where(User.is_active==True))

# Get a count of records
active_user_count = await User.count(query=User.where(User.is_active==True))
total_user_count = await User.count()

# Get the first record, ordered by a specific column
first_user_by_name = await User.first(order_by=User.name.asc())

# Get the most recently created/modified record (requires UpdateMixin)
latest_user = await User.last_created()
last_updated_user = await User.last_modified()
```

### Advanced Querying with `select()`

For more complex queries, use the `select()` method, which returns a SQLAlchemy `Select` object that you can chain.

```python
from sqlalchemy import or_

# Find all active users named Alice or Bob, ordered by name descending
query = (
    User.select().where(User.is_active == True, or_(User.name == "Alice", User.name == "Bob")).order_by(User.name.desc()).limit(10)
)

# Execute the query
selected_users = await User.all(query=query)
```

### Updating Records

```python
user = await User.find_by(name="Alice")
if user:
    user.name = "Alicia"
    await user.save(commit=True)
```

### Deleting Records

```python
user = await User.find_by(name="Bob")
if user:
    await User.delete(user, commit=True)
```

## Bulk Operations

For high-performance inserts, use `bulk_insert`.

```python
from sqlalchemy.exc import IntegrityError

users_to_bulk_insert = [
    User(name="Eve", email="eve@example.com"),
    User(name="Frank", email="frank@example.com"),
]

# This will raise an error if a user with the same email already exists
try:
    await User.bulk_insert(users_to_bulk_insert)
except IntegrityError:
    print("A user with that email already exists.")


# To skip duplicates instead of failing:
conflicting_users = [
    User(name="Alice", email="alice@example.com"),  # Assumes Alice exists
    User(name="Grace", email="grace@example.com"),
]
# 'on_conflict_index_elements' targets the unique constraint on the 'email' column
inserted = await User.bulk_insert(conflicting_users, on_conflict="nothing", on_conflict_index_elements=["email"])
# `inserted` will only contain Grace, as Alice was skipped.
```

## Pydantic Schemas & FastAPI Integration

Achemy makes it trivial to use your database models in an API framework like FastAPI by automatically generating Pydantic schemas.

### Automatic Schema Generation

You can get a Pydantic schema class directly from your model, which is perfect for API responses.

```python
from models import User

# Get the auto-generated Pydantic schema class
UserSchema = User.pydantic_schema()

# You can now use UserSchema like any other Pydantic model
# For example, to inspect its JSON schema for OpenAPI documentation
print(UserSchema.model_json_schema())
```

You can also convert a model instance directly to a Pydantic instance:

```python
user_instance = await User.find_by(name="Alice")
if user_instance:
    pydantic_user = user_instance.to_pydantic()
    print(pydantic_user.model_dump())
    # Output: {'id': UUID('...'), 'name': 'Alicia', 'email': '...', ...}
```

### Full FastAPI Example

Here’s how to build a simple User API. For API *input*, it's best practice to define a specific Pydantic model with only the fields a client should provide. For API *output*, we can use the automatically generated schema.

```python
# api.py
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr

from achemy import ActiveEngine, ActiveRecord
from config import db_config  # Assuming you have a config.py
from models import User  # Assuming you have a models.py


# --- FastAPI App Setup ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize ActiveEngine on startup
    engine = ActiveEngine(db_config)
    ActiveRecord.set_engine(engine)
    print("Database engine initialized.")
    yield
    # Dispose engines on shutdown
    await engine.dispose_engines()
    print("Database engines disposed.")


app = FastAPI(lifespan=lifespan)


# --- Pydantic Schemas ---

# 1. Define a schema for creating a user (API input)
class UserIn(BaseModel):
    name: str
    email: EmailStr


# 2. Use the auto-generated schema for responses (API output)
UserOut = User.pydantic_schema()


# --- API Endpoints ---
@app.post("/users/", response_model=UserOut, status_code=201)
async def create_user(user_in: UserIn):
    """Create a new user."""
    # Check if user already exists
    existing_user = await User.find_by(email=user_in.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered.")

    # Convert the input Pydantic model to a SQLAlchemy model instance
    user_model = User(**user_in.model_dump())

    # Save the model to the database
    await user_model.save(commit=True)

    # FastAPI automatically serializes the returned SQLAlchemy model instance
    # using the `UserOut` response model.
    return user_model


@app.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: uuid.UUID):
    """Retrieve a user by their ID."""
    user = await User.find(user_id)  # PKMixin provides .find()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # FastAPI automatically serializes the User model instance
    # into our Pydantic `UserOut` schema for the response.
    return user
```
To run this example, you would need `fastapi` and `uvicorn`:
```bash
pip install fastapi "uvicorn[standard]"
uvicorn api:app --reload
```

## Data Handling & Serialization

Achemy models provide helper methods for data conversion:

```python
user = await User.find_by(name="Alicia")

# Convert model to a dictionary (mapped columns only)
user_dict = user.to_dict()
# {'id': UUID('...'), 'name': 'Alicia', 'email': '...', ...}

# Convert to a JSON-serializable dictionary (handles UUID, datetime)
user_json = user.dump_model()
# {'id': '...', 'name': 'Alicia', 'email': '...', ...}

# Load data from a dictionary into a new model instance
new_user_data = {"name": "Eve", "email": "eve@example.com"}
new_user_instance = User.load(new_user_data)
# new_user_instance is now a transient User object
```

## Explicit Session Management & Transactions

While Achemy methods often handle sessions internally, you can manage them explicitly for transactions spanning multiple operations. Use `Model.get_session()` with an `async with` block for automatic commit/rollback handling.

```python
from models import City  # Assuming another model exists


async def complex_operation():
    async with await User.get_session() as session:
        try:
            user_frank = User(name="Frank", email="frank@acme.com")
            # Pass the explicit session, and set commit=False
            await User.add(user_frank, commit=False, session=session)

            city = City(name="Frankfurt", population=750000)
            await city.save(commit=False, session=session)

            # All operations will be committed together here
            await session.commit()
            print("Transaction committed successfully.")

        except Exception as e:
            print(f"An error occurred: {e}. Transaction will be rolled back.")
            # Rollback happens automatically when the 'async with' block exits on an error.
```

## Mixins

Achemy provides helpful mixins to reduce boilerplate:

*   **`PKMixin`**: Adds a standard `id: Mapped[uuid.UUID]` primary key with a default UUID factory. Also adds the `find(pk)` classmethod as a convenient alias for `get(pk)`.
*   **`UpdateMixin`**: Adds `created_at` and `updated_at` timestamp columns with automatic management. Provides classmethods like `last_created()`, `first_created()`, `last_modified()`, and `get_since(datetime)`.

```python
from sqlalchemy.orm import Mapped, mapped_column

from achemy import Base, PKMixin, UpdateMixin


class MyModel(Base, PKMixin, UpdateMixin):
    __tablename__ = "my_models"
    name: Mapped[str] = mapped_column()


# MyModel now has id, created_at, updated_at columns and related methods.
latest = await MyModel.last_modified()
instance = await MyModel.find(some_uuid)
```

## Examples

For more comprehensive examples, refer to the following:

*   `achemy/demo/amodels.py`: Sample asynchronous model definitions.
*   `tests/`: Unit and integration tests showcasing various features.
