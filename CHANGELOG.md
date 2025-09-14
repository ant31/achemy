# Changelog

## 0.3.0 (2025-09-14)

### 💥 Breaking Changes

-   **Mandatory Explicit Session Management**: The library now requires an explicit `AsyncSession` object to be passed to all database-interacting methods (e.g., `.all()`, `.save()`, `.find_by()`, etc.). The previous behavior of automatically creating a temporary session for single operations has been removed.

    **Reasoning**: Implicit session management was identified as a major architectural flaw. While convenient for simple scripts, it was inefficient (creating many sessions/connections) and transactionally unsafe in production applications. Enforcing explicit session management via the `async with Model.get_session() as session:` pattern makes code safer, more performant, and easier to reason about.

    **Migration Guide**:
    All calls to Achemy methods must now be wrapped in a session block and have the session passed to them.

    **Before (v0.2.x):**
    ```python
    # Simple query (implicit session)
    user = await User.find_by(name="Alice")

    # Transaction (explicit session)
    async with await User.get_session() as session:
        user = await User.find_by(name="Alice", session=session)
        if user:
            user.name = "Alicia"
            await user.save(commit=True, session=session)
    ```

    **After (v0.3.0):**
    ```python
    # All operations require an explicit session
    async with User.get_session() as session:
        user = await User.find_by(session, name="Alice")
        if user:
            user.name = "Alicia"
            # Note: commit is handled by the session context manager
            await user.save(session=session)
            await session.commit()
    ```
