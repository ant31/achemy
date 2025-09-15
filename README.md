# Achemy Documentation

Achemy is an asynchronous Python library that serves as a toolkit for SQLAlchemy 2.0+, designed to streamline database interactions and promote best practices like the Repository pattern. It provides a powerful base model, a fluent query-building interface, and seamless Pydantic integration.

## Features

-   **Standardized Foundation**: Homogenize database configuration and data access patterns across multiple projects, reducing boilerplate and improving consistency.
-   **Repository Pattern Support**: A generic `BaseRepository` provides common data access logic, encouraging robust and testable data access layers.
-   **Fluent Query Interface**: Chainable, repository-centric methods for building complex queries (`repo.where(...)`).
-   **Async First**: Built from the ground up for modern asynchronous applications with `async/await`.
-   **Explicit Session Management**: Achemy enforces safe, explicit session and transaction handling via SQLAlchemy's Unit of Work pattern.
-   **Pydantic Integration**: Automatically generate Pydantic schemas from your SQLAlchemy models for rapid prototyping.
-   **Bulk Operations**: Efficiently insert large numbers of records with support for conflict resolution.
-   **Helpful Mixins**: Common patterns like UUID primary keys (`PKMixin`) and timestamp tracking (`UpdateMixin`) are available as simple mixins.

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


# Create a common base for models.
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
from sqlalchemy.ext.asyncio import AsyncSession

from achemy import ActiveEngine
from config import db_config
from models import User

# --- Repository for Data Access ---
from achemy import BaseRepository

class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def create(self, name: str, email: str) -> User:
        """Creates and saves a new user."""
        new_user = User(name=name, email=email)
        # BaseRepository provides the .save() method
        await self.save(new_user)
        return new_user

    async def get_by_email(self, email: str) -> User | None:
        """Finds a user by their email."""
        # BaseRepository provides the .find_by() method
        return await self.find_by(email=email)

# --- Application Entry Point ---
# Create the engine instance. This should be a singleton in your application.
engine = ActiveEngine(db_config)

# Get a session factory from the engine.
_db_engine, session_factory = engine.session()

async def main():
    # Business logic is responsible for the session and transaction.
    async with session_factory() as session:
        # Business logic interacts with the repository, not the models directly.
        repo = UserRepository(session)

        user = await repo.get_by_email("alice@example.com")
        if not user:
            user = await repo.create(name="Alice", email="alice@example.com")
            await session.commit()
            print(f"Created user: {user}")
        else:
            print(f"Found user: {user}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Using the Repository Pattern

Achemy is designed to support the **Repository Pattern**, which separates your business logic from the data access logic. Your models remain simple data containers, while repositories handle all database interactions.

First, create a base model for your application. It does not need any special mixins for querying.

```python
# models.py
# ...
from achemy import Base, PKMixin, UpdateMixin

class AppBase(Base):
    __abstract__ = True

class User(AppBase, PKMixin, UpdateMixin):
    # ...
```

### Example: `UserRepository`

Here is a repository for the `User` model. By inheriting from `BaseRepository`, it gains a suite of helpful data access methods (`.add`, `.get`, `.find_by`, `.all`, `.delete`, etc.). You can then add your own business-specific query methods.

```python
# repositories.py
from sqlalchemy.ext.asyncio import AsyncSession
from achemy import BaseRepository
from models import User

class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def create(self, name: str, email: str) -> User:
        """Creates a new user instance and adds it to the session."""
        user = User(name=name, email=email)
        await self.add(user) # .add() is inherited
        return user

    async def get_active_users(self) -> list[User]:
        """Returns all active users."""
        query = self.where(User.is_active == True).order_by(User.name)
        return await self.all(query=query)

    # Note: Methods like get_by_id, get_by_email, and delete are often
    # not needed, as you can directly use the inherited methods:
    # repo.get(user_id)
    # repo.find_by(email=email)
    # repo.delete(user)
```

### Using the Repository in Business Logic

Your application or business logic controls the session and transaction. It creates a repository instance and calls its methods.

```python
# Assume 'session_factory' is an initialized sessionmaker.
async with session_factory() as session:
    repo = UserRepository(session)

    # --- Create ---
    new_user = await repo.create(name="Alice", email="alice@example.com")

    # --- Update ---
    user_to_update = await repo.get_by_email("alice@example.com")
    if user_to_update:
        repo.update(user_to_update, new_name="Alicia")

    # --- Delete ---
    user_to_delete = await repo.get_by_email("bob@example.com")
    if user_to_delete:
        await repo.delete(user_to_delete)

    # The business logic is responsible for the commit.
    # All changes (create, update, delete) are persisted in one transaction.
    await session.commit()
```

## Bulk Operations

For high-performance inserts, `bulk_insert` can be exposed through your repository.

```python
# In your UserRepository:
async def bulk_create(self, users_data: list[dict]) -> list[User]:
    """Efficiently creates multiple users, skipping conflicts on email."""
    users = [User(**data) for data in users_data]
    inserted_users = await self.bulk_insert(
        users,
        on_conflict="nothing",
        on_conflict_index_elements=["email"], # Assumes unique constraint on email
        commit=False, # The business logic will handle the commit
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
async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency to create and clean up a session per request."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session

def get_user_repo(session: AsyncSession = Depends(get_db_session)) -> UserRepository:
    """FastAPI dependency that provides a UserRepository instance."""
    return UserRepository(session)


# --- API Endpoints ---
@app.post("/users/", response_model=UserOut, status_code=201)
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


@app.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: uuid.UUID, repo: UserRepository = Depends(get_user_repo)):
    """Retrieve a user by their ID."""
    user = await repo.get(user_id)  # .get() is inherited from BaseRepository
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # The User model instance is automatically serialized by FastAPI
    # into our Pydantic `UserOut` schema for the response.
    return user
```

### Schema Generation with the CLI (Recommended)

To bridge the gap between SQLAlchemy models and Pydantic schemas without sacrificing type safety, Achemy includes a command-line tool to automatically generate static, type-safe Pydantic models from your `AlchemyModel` definitions.

This is the recommended approach for integrating with APIs and ensuring your code is fully type-checkable.

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

This command will inspect `your_app/models.py`, find all `AlchemyModel` subclasses, and generate a `your_app/schemas.py` file containing corresponding Pydantic `BaseModel` classes.

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
# Assume 'session_factory' has been created from your ActiveEngine instance,
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

*   **`PKMixin`**: Adds a standard `id: Mapped[uuid.UUID]` primary key.
*   **`UpdateMixin`**: Adds `created_at` and `updated_at` timestamp columns with automatic management. All query logic (e.g., finding the last modified record) should be implemented in your repository classes.

```python
from sqlalchemy.orm import Mapped, mapped_column

from achemy import Base, PKMixin, UpdateMixin


class MyModel(Base, PKMixin, UpdateMixin):
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
