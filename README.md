# Achemy Documentation

Achemy is an asynchronous Python library that simplifies database interactions by providing an Active Record pattern implementation built on SQLAlchemy 2.0+. It focuses on async operations, automatic session management, and seamless Pydantic integration for ease of use.

## Features

-   **Active Record Pattern**: Intuitive, model-centric methods for database operations (`User.all()`, `user.save()`).
-   **Async First**: Built for modern asynchronous applications with `async/await`.
-   **Explicit Session Management**: Achemy enforces safe, explicit session and transaction handling, preventing common performance and data integrity pitfalls.
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

### Step 3: Initialize and Use the Engine

In your application's entry point, create the `ActiveEngine`. You will use this engine instance to create sessions for your database operations.

```python
# main.py
import asyncio

from achemy import ActiveEngine
from config import db_config
from models import User

# Create the engine instance. This should be a singleton in your application.
engine = ActiveEngine(db_config)

# Get a session factory from the engine.
_db_engine, session_factory = engine.session()


async def main():
    # Your application logic here
    # Example: create a user
    async with session_factory() as session:
        new_user = User(name="Alice", email="alice@example.com")
        await new_user.save(session=session)
        await session.commit()
        print(f"Created user: {new_user}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Basic CRUD Operations

### Creating and Saving Records

All database operations must be performed within an explicit session context. You get a session from a session factory, which is created by your `ActiveEngine` instance. This ensures proper transaction management and connection handling. Commits must be handled on the session object.

```python
# Assume 'engine' is an initialized ActiveEngine instance
_db_engine, session_factory = engine.session()

async with session_factory() as session:
    # Create an instance and save it.
    user = User(name="Alice", email="alice@example.com")
    await user.save(session=session)

    # Use the class method 'add'.
    user_bob = User(name="Bob", email="bob@example.com")
    await User.add(user_bob, session=session)

    # Add multiple records at once
    users_to_add = [User(name="Charlie", email="charlie@example.com"), User(name="Diana", email="diana@example.com")]
    await User.add_all(users_to_add, session=session)

    # The changes are only flushed to the DB at this point.
    # To persist them, commit the session:
    await session.commit()
```
The session context manager automatically handles rollback on exceptions. See the section on Transactions for more details.

### Querying Records

```python
# Assume 'session_factory' has been created from your ActiveEngine instance.
async with session_factory() as session:
    # Get all users (use with caution on large tables)
    all_users = await User.all(session)

    # Get a user by primary key (highly optimized)
    user_by_pk = await User.get(session, some_uuid)

    # Find a user by primary key using the PKMixin helper 'find'
    # (This is equivalent to User.get(pk))
    user_by_find = await User.find(session, some_uuid)

    # Find the first user matching specific criteria
    user_by_email = await User.find_by(session, email="alice@example.com")

    # Find all users matching criteria
    active_users = await User.all(session, query=User.where(User.is_active==True))

    # Get a count of records
    active_user_count = await User.count(session, query=User.where(User.is_active==True))
    total_user_count = await User.count(session)

    # Get the first record, ordered by a specific column
    first_user_by_name = await User.first(session, order_by=User.name.asc())

    # Get the most recently created/modified record (requires UpdateMixin)
    latest_user = await User.last_created(session)
    last_updated_user = await User.last_modified(session)
```

### Advanced Querying with `select()`

For more complex queries, use the `select()` method, which returns a SQLAlchemy `Select` object that you can chain.

```python
from sqlalchemy import or_

# Find all active users named Alice or Bob, ordered by name descending
query = (
    User.select().where(User.is_active == True, or_(User.name == "Alice", User.name == "Bob")).order_by(User.name.desc()).limit(10)
)

# Execute the query within a session
# Assume 'session_factory' has been created from your ActiveEngine instance.
async with session_factory() as session:
    selected_users = await User.all(session, query=query)
```

### Updating Records

```python
# Assume 'session_factory' has been created from your ActiveEngine instance.
async with session_factory() as session:
    user = await User.find_by(session, name="Alice")
    if user:
        user.name = "Alicia"
        await user.save(session=session)
        await session.commit()
```

### Deleting Records

```python
# Assume 'session_factory' has been created from your ActiveEngine instance.
async with session_factory() as session:
    user = await User.find_by(session, name="Bob")
    if user:
        await User.delete(user, session=session)
        await session.commit()
```

## Bulk Operations

For high-performance inserts, use `bulk_insert`.

```python
# Assume 'session_factory' has been created from your ActiveEngine instance.
from sqlalchemy.exc import IntegrityError

async with session_factory() as session:
    users_to_bulk_insert = [
        User(name="Eve", email="eve@example.com"),
        User(name="Frank", email="frank@example.com"),
    ]

    # This will raise an error if a user with the same email already exists
    try:
        await User.bulk_insert(users_to_bulk_insert, session)
        await session.commit()
    except IntegrityError:
        print("A user with that email already exists.")
        # The session context manager automatically rolls back on exception.

    # To skip duplicates instead of failing:
    conflicting_users = [
        User(name="Alice", email="alice@example.com"),  # Assumes Alice exists
        User(name="Grace", email="grace@example.com"),
    ]
    # 'on_conflict_index_elements' targets the unique constraint on the 'email' column
    inserted = await User.bulk_insert(
        conflicting_users, session, on_conflict="nothing", on_conflict_index_elements=["email"]
    )
    await session.commit()
    # `inserted` will only contain Grace, as Alice was skipped.
```

## Pydantic Schemas & FastAPI Integration

Achemy models can be easily integrated with Pydantic, which is essential for building robust APIs with frameworks like FastAPI. For production applications that value type safety, **manually defining Pydantic schemas is the recommended best practice.**

### Full FastAPI Example (Recommended Approach)

Here’s how to build a simple User API. For API *input* and *output*, we will define explicit Pydantic models. This ensures your API contract is clear, validated, and fully supported by static type checkers like Mypy.

```python
# api.py
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from achemy import ActiveEngine
from config import db_config  # Assuming you have a config.py
from models import User  # Assuming you have a models.py


# --- FastAPI App Setup ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize ActiveEngine on startup
    engine = ActiveEngine(db_config)
    _db_engine, session_factory = engine.session()
    # Store engine and session factory in the app's state
    app.state.engine = engine
    app.state.session_factory = session_factory
    print("Database engine initialized.")
    yield
    # Dispose engines on shutdown
    await app.state.engine.dispose_engines()
    print("Database engines disposed.")


app = FastAPI(lifespan=lifespan)


# --- Pydantic Schemas ---

# 1. Define a schema for creating a user (API input)
class UserIn(BaseModel):
    name: str
    email: EmailStr


# 2. Define a schema for user data in responses (API output)
# This provides full type safety and editor autocompletion.
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: EmailStr
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Session Dependency ---
async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency to create and clean up a session per request."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


# --- API Endpoints ---
@app.post("/users/", response_model=UserOut, status_code=201)
async def create_user(user_in: UserIn, session: AsyncSession = Depends(get_db_session)):
    """Create a new user."""
    # The session is now managed by the dependency.
    # Check if user already exists
    existing_user = await User.find_by(session, email=user_in.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered.")

    # Convert the input Pydantic model to a SQLAlchemy model instance
    user_model = User(**user_in.model_dump())

    # Save the model to the database
    await user_model.save(session=session)
    await session.commit()

    # The dependency handles rollback on exceptions.
    # The user_model is now persisted and can be returned.
    return user_model


@app.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    """Retrieve a user by their ID."""
    # The session is now managed by the dependency.
    user = await User.find(session, user_id)  # PKMixin provides .find()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # The User model instance is automatically serialized by FastAPI
    # into our Pydantic `UserOut` schema for the response.
    return user
```

### Automatic Schema Generation (For Prototyping)

Achemy provides a convenience method, `Model.pydantic_schema()`, to generate a Pydantic schema from a model at runtime. This can be useful for quick prototyping or internal tools where strict type safety is not a primary concern.

```python
from models import User

# Get the auto-generated Pydantic schema class
UserSchema = User.pydantic_schema()

# Convert a model instance directly to a Pydantic instance
# Assume 'session_factory' has been created from your ActiveEngine instance.
async with session_factory() as session:
    user_instance = await User.find_by(session, name="Alice")
    if user_instance:
        pydantic_user = user_instance.to_pydantic()
        print(pydantic_user.model_dump())
```

> **Warning**: Because these schemas are created dynamically, static type checkers (like Mypy) and IDEs cannot infer their fields. This will lead to type errors and a lack of autocompletion. For any production-facing code, the recommended approach is to define schemas manually as shown in the FastAPI example above.
To run this example, you would need `fastapi` and `uvicorn`:
```bash
pip install fastapi "uvicorn[standard]"
uvicorn api:app --reload
```

## Data Handling & Serialization

Achemy models provide helper methods for data conversion:

```python
# Assume 'session_factory' has been created from your ActiveEngine instance.
async with session_factory() as session:
    user = await User.find_by(session, name="Alicia")

if user:
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

## Transactions and Session Management

Achemy requires explicit session management for all database operations. This ensures that every action is part of a well-defined transaction, providing data integrity and optimal performance.

The standard pattern is to get a session factory from your `ActiveEngine` instance and use it within an `async with` block. This block creates a session and a transaction. If the block completes successfully, you can commit the transaction with `await session.commit()`. If an exception occurs, the transaction is automatically rolled back.

```python
from models import City  # Assuming another model exists


async def complex_operation():
    # Assume 'session_factory' has been created from your ActiveEngine instance.
    async with session_factory() as session:
        try:
            user_frank = User(name="Frank", email="frank@acme.com")
            # Pass the explicit session to all operations
            await User.add(user_frank, session=session)

            city = City(name="Frankfurt", population=750000)
            await city.save(session=session)

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
