from app.room_auth import RoomTokenSigner


def test_room_token_is_bound_to_application_id() -> None:
    signer = RoomTokenSigner("a-test-secret-longer-than-sixteen-characters")
    token = signer.issue("app_alpha")

    assert signer.verify("app_alpha", token)
    assert not signer.verify("app_beta", token)
    assert not signer.verify("app_alpha", token + "x")
    assert not signer.verify("app_alpha", "")


def test_room_token_rejects_short_signing_secret() -> None:
    try:
        RoomTokenSigner("too-short")
    except ValueError as error:
        assert "at least 16" in str(error)
    else:
        raise AssertionError("short room secrets must be rejected")
