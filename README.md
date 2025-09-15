# Achemy Documentation

Achemy is an asynchronous Python library that serves as a toolkit for SQLAlchemy 2.0+, designed to streamline database interactions and promote best practices like the Repository pattern. It provides a powerful base model, a fluent query-building interface, and seamless Pydantic integration.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Getting Started: A Complete Example](#getting-started-a-complete-example)
  - [Step 1: Configuration](#step-1-configuration)
  - [Step 2: Engine and Model Setup](#step-2-engine-and-model-setup)
  - [Step 3: Define a Repository](#step-3-define-a-repository)
  - [Step 4: Use the Repository in Your Application](#step-4-use-the-repository-in-your-application)
- [Bulk Operations](#bulk-operations)
- [Pydantic Schemas & FastAPI Integration](#pydantic-schemas--fastapi-integration)
  - [Full FastAPI Example](#full-fastapi-example)
  - [Generating Schemas with the CLI](#generating-schemas-with-the-cli)
- [Data Handling & Serialization](#data-handling--serialization)
- [Simplified Usage for Scripts and Tests](#simplified-usage-for-scripts-and-tests)
- [Transactions and the Unit of Work](#transactions-and-the-unit-of-work)
- [Mixins](#mixins)
- [Examples](#examples)

## Features

-   **Standardized Foundation**: Homogenize database configuration and data access patterns across multiple projects, reducing boilerplate and improving consistency.
-   **Repository Pattern Support**: A generic `BaseRepository` provides common data access logic, encouraging robust and testable data access layers.
-   **Fluent Query Interface**: Chainable, repository-centric methods for building complex queries (`repo.where(...)`).
-   **Async First**: Built from the ground up for modern asynchronous applications with `async/await`.
-   **Explicit Session Management**: Achemy enforces safe, explicit session and transaction handling via SQLAlchemy's Unit of Work pattern.
-   **Pydantic Integration**: Automatically generate Pydantic schemas from your SQLAlchemy models for rapid prototyping.
-   **Bulk Operations**: Efficiently insert large numbers of records with support for conflict resolution.
-   **Helpful Mixins**: Common patterns like UUID primary keys (`UUIDPKMixin`), integer primary keys (`IntPKMixin`), and timestamp tracking (`UpdateMixin`) are available as simple mixins.

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
from achemy.config import DatabaseConfig

db_config = DatabaseConfig(
    db="mydatabase",
    user="myuser",
    password="mypassword",
    host="localhost",
    port=5432,
)
```
See `achemy/config.py` for more options.

### Step 2: Engine and Model Setup

Initialize the `AchemyEngine` and define your models. It's good practice to create a common base class for your models.

```python
# models.py
from sqlalchemy.orm import Mapped, mapped_column

from achemy import Base, UpdateMixin, UUIDPKMixin


# Create a common base for models.
class AppBase(Base):
    __abstract__ = True
    # You can add shared logic or configurations here


class User(AppBase, UUIDPKMixin, UpdateMixin):
    """A user model with UUID primary key and timestamps."""

    __tablename__ = "users"

    name: Mapped[str] = mapped_column()
    email: Mapped[str] = mapped_column(unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
```

### Step 3: Define a Repository

Achemy is designed to support the **Repository Pattern**. Repositories handle all database interactions, keeping your business logic clean and your data access logic centralized and testable.

Create a repository for your `User` model. By inheriting from `BaseRepository`, it automatically gains a suite of helpful data access methods (`.get`, `.find_by`, `.all`, `.delete`, etc.).

```python
# repositories.py
from sqlalchemy.ext.asyncio import AsyncSession
from achemy import BaseRepository
from models import User

class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def get_active_users(self) -> list[User]:
        """Returns all active users, ordered by name."""
        query = self.where(User.is_active == True).order_by(User.name)
        return await self.all(query=query)

    # Note: Methods like get by ID or find by a specific field are often
    # not needed, as you can directly use the inherited methods from your code:
    # user = await repo.get(user_id)
    # user = await repo.find_by(email=email)
```

### Step 4: Use the Repository in Your Application

Your application's entry point is responsible for creating the `AchemyEngine`, managing the session, and controlling transactions (the Unit of Work).

```python
# main.py
import asyncio
from config import db_config
from models import AppBase, User
from repositories import UserRepository
from achemy import AchemyEngine

# Create a single, shared engine instance for your application.
engine = AchemyEngine(db_config)
db_engine, session_factory = engine.session()

async def create_tables():
    """A utility function to create database tables."""
    async with db_engine.begin() as conn:
        # Drop all tables and recreate them. For production, use Alembic.
        await conn.run_sync(AppBase.metadata.drop_all)
        await conn.run_sync(AppBase.metadata.create_all)
    print("Tables created.")

async def main():
    # Before running, create the necessary tables.
    await create_tables()

    # The business logic is responsible for the session and transaction.
    async with session_factory() as session:
        repo = UserRepository(session)

        # --- Create ---
        print("Creating user...")
        existing_user = await repo.find_by(email="alice@example.com")
        if not existing_user:
            new_user = User(name="Alice", email="alice@example.com")
            await repo.save(new_user) # .save() is an alias for .add()
            await session.commit()
            print(f"User created: {new_user.id}")
        else:
            print("User 'alice@example.com' already exists.")

        # --- Query ---
        print("\nFinding active users...")
        active_users = await repo.get_active_users()
        for user in active_users:
            print(f" - Found active user: {user.name}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Bulk Operations

For high-performance inserts, `bulk_insert` can be exposed through your repository.

```python
# In your UserRepository:
async def bulk_create(self, users_data: list[dict]) -> list[User]:
    """Efficiently creates multiple users, skipping conflicts on email."""
    inserted_users = await self.bulk_insert(
        users_data,
        on_conflict="nothing",
        on_conflict_index_elements=["email"],  # Assumes unique constraint on email
        commit=False,  # The business logic will handle the commit
    )
    return inserted_users

# In your business logic:
async with session_factory() as session:
    repo = UserRepository(session)
    user_data = [
        {"name": "Eve", "email": "eve@example.com"},
        {"name": "Alice", "email": "alice@example.com"}, # Assumes Alice exists
        {"name": "Frank", "email": "frank@example.com"},
    ]
    inserted = await repo.bulk_create(user_data)
    await session.commit()
    # `inserted` will contain Eve and Frank, as Alice was skipped.
```

## Pydantic Schemas & FastAPI Integration

Achemy models can be easily integrated with Pydantic, which is essential for building robust APIs with frameworks like FastAPI. The recommended workflow is to use the `achemy` CLI to generate a baseline set of Pydantic schemas from your models, and then create specialized schemas for your API inputs (e.g., `UserIn`) as needed.

### Full FastAPI Example

Here’s how to build a simple User API. We will use a generated schema for API output (`UserSchema`) and a manually defined schema for API input (`UserIn`). This ensures your API contract is clear, validated, and fully supported by static type checkers.

```python
# api.py
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from achemy import AchemyEngine
from config import db_config  # Assuming you have a config.py
from models import User  # Assuming you have a models.py


# --- FastAPI App Setup ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize AchemyEngine on startup
    engine = AchemyEngine(db_config)
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


# 2. Import the auto-generated schema for API output.
# We assume you have run `achemy generate-schemas` to create this.
from schemas import UserSchema  # Assuming a schemas.py file exists


# --- Session Dependency ---
async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency to create and clean up a session per request."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


# --- Repository for Data Access ---
# (You would typically place this in its own repositories.py file)
from achemy import BaseRepository

class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def create_from_schema(self, user_in: "UserIn") -> User:
        """Creates a new user instance from a Pydantic schema."""
        user = User(**user_in.model_dump())
        await self.save(user)
        return user

    # .get() is inherited from BaseRepository and can be used directly.
    # .find_by() is also inherited.


# --- Session and Repository Dependencies ---
def get_user_repo(session: AsyncSession = Depends(get_db_session)) -> UserRepository:
    """FastAPI dependency that provides a UserRepository instance."""
    return UserRepository(session)


# --- API Endpoints ---
# Use the generated schema for the response model to ensure it matches the DB model.
@app.post("/users/", response_model=UserSchema, status_code=201)
async def create_user(user_in: UserIn, repo: UserRepository = Depends(get_user_repo)):
    """Create a new user."""
    # Check if user already exists (using inherited method)
    existing_user = await repo.find_by(email=user_in.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered.")

    # The repository handles creating the model instance
    user = await repo.create_from_schema(user_in)

    # The business logic (endpoint) is responsible for the commit.
    await repo.session.commit()

    # After commit, the user object is refreshed and can be returned.
    return user


@app.get("/users/{user_id}", response_model=UserSchema)
async def get_user(user_id: uuid.UUID, repo: UserRepository = Depends(get_user_repo)):
    """Retrieve a user by their ID."""
    user = await repo.get(user_id)  # .get() is inherited from BaseRepository
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # The User model instance is automatically serialized by FastAPI
    # into our Pydantic `UserSchema` for the response.
    return user
```

### Generating Schemas with the CLI

Achemy includes a command-line tool to automatically generate static, type-safe Pydantic models from your model definitions (those inheriting from `achemy.Base`). This is the recommended first step for integrating your database models with an API.

#### Step 1: Install Typer

The CLI tool requires `typer`.

```bash
pip install "typer[all]"
```

#### Step 2: Run the Generator

From your project's root directory, run the `generate-schemas` command. You need to provide the Python import path to your models module and specify an output file.

```bash
python -m achemy.cli generate-schemas your_app.models --output your_app/schemas.py
```

This command will inspect `your_app/models.py`, find all models inheriting from `achemy.Base`, and generate a `your_app/schemas.py` file containing corresponding Pydantic `BaseModel` classes.

#### Step 3: Use the Generated Schemas

The generated file can be imported and used like any other manually created Pydantic schema, with full support for static analysis and autocompletion.

```python
# In your FastAPI app:
from your_app.schemas import UserSchema

@app.get("/users/{user_id}", response_model=UserSchema)
async def get_user(user_id: uuid.UUID, repo: UserRepository = Depends(get_user_repo)):
    # ...
```

## Data Handling & Serialization

Achemy models provide helper methods for data conversion:

```python
# Assume 'session_factory' has been created from your AchemyEngine instance,
# and you have a UserRepository as defined in previous examples.
async with session_factory() as session:
    repo = UserRepository(session)
    user = await repo.find_by(name="Alicia")

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

## Simplified Usage for Scripts and Tests

For simple use cases like data migration scripts, automated tasks, or tests, managing the session factory and repository instances can be verbose. Achemy provides a convenient `engine.repository()` context manager that handles this for you.

It automatically creates a session, provides a `BaseRepository` for a given model, and manages the transaction (commit on success, rollback on error).

**Note:** This pattern is recommended for self-contained, short-lived tasks. For larger applications, especially web servers like FastAPI, the explicit session management pattern shown in the main examples is strongly recommended to ensure correct transaction scoping.

```python
# script.py
import asyncio
from config import db_config
from models import User
from achemy import AchemyEngine

# Create a single, shared engine instance.
engine = AchemyEngine(db_config)

async def add_admin_user():
    """A simple script to add a user if they don't exist."""
    admin_email = "admin@example.com"

    # Use the context manager to get a repository with a managed session.
    async with engine.repository(User) as repo:
        existing_user = await repo.find_by(email=admin_email)
        if not existing_user:
            print(f"Creating user: {admin_email}")
            admin_user = User(name="Admin", email=admin_email, is_active=True)
            await repo.save(admin_user)
            # No need to call session.commit() - it's handled automatically.
        else:
            print(f"User {admin_email} already exists.")

if __name__ == "__main__":
    asyncio.run(add_admin_user())
```

## Transactions and the Unit of Work

Achemy embraces SQLAlchemy's **Unit of Work** pattern. The `AsyncSession` object tracks all changes to your models (creations, updates, deletions) within a single transactional scope.

Your business logic is responsible for defining this scope. The standard pattern is to create a session from your session factory, pass it to your repositories, and then call `await session.commit()` once all operations for that unit of work are complete. The `async with` block ensures that the transaction is automatically rolled back if an exception occurs.

```python
# repositories.py
# (Define UserRepository and CityRepository here)

async def create_user_and_hometown(user_data: dict, city_data: dict):
    # Assume 'session_factory' has been created.
    async with session_factory() as session:
        user_repo = UserRepository(session)
        city_repo = CityRepository(session)

        try:
            # Step 1: Create a new city
            city = await city_repo.create(**city_data)

            # Step 2: Create a new user
            user = await user_repo.create(**user_data)
            
            # This is a single unit of work. Both the user and city will be
            # created, or neither will be if an error occurs.
            await session.commit()
            print("Transaction committed successfully.")

        except Exception as e:
            print(f"An error occurred: {e}. Transaction will be rolled back.")
            # Rollback happens automatically when the 'async with' block exits on an error.
```

## Mixins

Achemy provides helpful mixins to reduce model definition boilerplate.

*   **`UUIDPKMixin`**: Adds a standard `id: Mapped[uuid.UUID]` primary key with a client-side default.
*   **`PGUUIDPKMixin`**: For PostgreSQL, adds a UUID primary key that uses the server-side `gen_random_uuid()` function for generation.
*   **`IntPKMixin`**: Adds a standard `id: Mapped[int]` auto-incrementing primary key.
*   **`UpdateMixin`**: Adds `created_at` and `updated_at` timestamp columns with automatic management.

```python
from sqlalchemy.orm import Mapped, mapped_column

from achemy import Base, UpdateMixin, UUIDPKMixin


class MyModel(Base, UUIDPKMixin, UpdateMixin):
    __tablename__ = "my_models"
    name: Mapped[str] = mapped_column()


# MyModel now has id, created_at, and updated_at columns.
# All database operations should be performed via a repository.
# Assume you have a session from a session factory and a MyModelRepository.
async with session_factory() as session:
    repo = MyModelRepository(session)
    # Example of a custom repository method:
    # latest = await repo.find_last_modified()
    # To find an instance by its primary key, use the inherited .get() method:
    instance = await repo.get(some_uuid)
```

## Examples

For more comprehensive examples, refer to the following:

*   `achemy/demo/amodels.py`: Sample asynchronous model definitions.
*   `tests/`: Unit and integration tests showcasing various features.
