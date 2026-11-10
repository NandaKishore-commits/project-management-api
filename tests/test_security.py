from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_is_hashed_not_stored_as_text():
    hashed = hash_password("Password123")
    assert hashed != "Password123"
    assert hashed.startswith("$2b$")
    assert verify_password("Password123", hashed) is True
    assert verify_password("WrongPass1", hashed) is False


def test_same_password_gives_different_hashes():
    # bcrypt adds a random salt, so two users with one password get different hashes
    assert hash_password("Password123") != hash_password("Password123")


def test_token_contains_the_user_id():
    token = create_access_token(7)
    assert decode_access_token(token)["sub"] == "7"