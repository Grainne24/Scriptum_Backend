import pytest
from app.routers.users import hash_password

'''This is to test the password hashing'''

class TestPasswordHashing:
    #This makes sure the stored hash is never the same as the original password
    def test_hash_is_not_plaintext(self):
        assert hash_password("mypassword123") != "mypassword123"

    #Hashing the same password should give the same result
    def test_same_password_produces_same_hash(self):
        assert hash_password("mypassword123") == hash_password("mypassword123")

    #Different passwords should never produce the same hash
    def test_different_passwords_produce_different_hashes(self):
        assert hash_password("password1") != hash_password("password2")

    #Make sure the SHA256 alway outputs 64 characters
    def test_hash_is_64_chars(self):
        assert len(hash_password("anything")) == 64

    #Make sure hashing an empty pasword does not crash
    def test_empty_string_still_hashes(self):
        result = hash_password("")
        assert isinstance(result, str)
        assert len(result) == 64

    #Make sure that passwords like 'Password' and 'password' are treated differently
    def test_case_sensitive(self):
        assert hash_password("Password") != hash_password("password")

'''This tests all of the user endpoints'''

class TestUserEndpoints:

    #A registration should fail if no email is provided
    def test_register_missing_email_returns_422(self, client):
        response = client.post("/users/", json={
            "username": "user",
            "password": "password123"
        })
        assert response.status_code == 422

    #The registration should fail if no password is provided
    def test_register_missing_password_returns_422(self, client):
        response = client.post("/users/", json={
            "email": "test@test.com",
            "username": "user2"
        })
        assert response.status_code == 422

    #A valid registration should return 201 and the users email
    def test_register_success(self, client):
        response = client.post("/users/", json={
            "email": "test@test.com",
            "username": "user24",
            "password": "password123",
            "first_name": "User",
            "last_name": "Test"
        })
        assert response.status_code == 201
        assert response.json()["email"] == "test@test.com"

    #If a user registers with an email already used it will return a 400 error
    def test_duplicate_email_rejected(self, client):
        payload = {
            "email": "test@test.com",
            "username": "user1",
            "password": "password123",
            "first_name": "A", "last_name": "B"
        }
        client.post("/users/", json=payload)
        response = client.post("/users/", json={**payload, "username": "user2"})
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    #If a user registers with a username which has already been used it will return an error
    def test_duplicate_username_rejected(self, client):
        client.post("/users/", json={
            "email": "first@test.com", "username": "samename",
            "password": "password123", "first_name": "A", "last_name": "B"
        })
        response = client.post("/users/", json={
            "email": "second@test.com", "username": "samename",
            "password": "password123", "first_name": "A", "last_name": "B"
        })
        assert response.status_code == 400

    #Correct email and password such retun a success response
    def test_login_success(self, client):
        client.post("/users/", json={
            "email": "login@test.com", "username": "loginuser",
            "password": "correct123", "first_name": "A", "last_name": "B"
        })
        response = client.post("/users/login", json={
            "email": "login@test.com", "password": "correct123"
        })
        assert response.status_code == 200

    #If a user logs a wrong password it should be rejected
    def test_login_wrong_password_returns_401(self, client):
        client.post("/users/", json={
            "email": "auth@test.com", "username": "authuser",
            "password": "correct123", "first_name": "A", "last_name": "B"
        })
        response = client.post("/users/login", json={
            "email": "auth@test.com", "password": "wrongpassword"
        })
        assert response.status_code == 401

    #If a user logs in with a non existent account it should return 401
    def test_login_nonexistent_user_returns_401(self, client):
        response = client.post("/users/login", json={
            "email": "nobody@test.com", "password": "password123"
        })
        assert response.status_code == 401

    #Users should be able to log in with their username and email
    def test_login_can_use_username_instead_of_email(self, client):
        client.post("/users/", json={
            "email": "byname@test.com", "username": "byusername",
            "password": "password123", "first_name": "A", "last_name": "B"
        })
        response = client.post("/users/login", json={
            "email": "byusername",
            "password": "password123"
        })
        assert response.status_code == 200

    #The API should never reveal the password hash in it response
    def test_response_does_not_contain_password_hash(self, client):
        response = client.post("/users/", json={
            "email": "safe@test.com", "username": "safeuser",
            "password": "password123", "first_name": "A", "last_name": "B"
        })
        body = response.json()
        assert "password_hash" not in body
        assert "password" not in body

    #Fetching a non-existent user ID returns a 404
    def test_get_nonexistent_user_returns_404(self, client):
        response = client.get("/users/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    #Passing a non UUID string returns a 422
    def test_invalid_uuid_returns_422(self, client):
        response = client.get("/users/not-a-uuid")
        assert response.status_code == 422