from app.id_factory import generate_application_id


def test_generate_application_id_prefix_and_uniqueness() -> None:
    generated = {generate_application_id("App") for _ in range(32)}
    assert len(generated) == 32
    for application_id in generated:
        assert application_id.startswith("app_")
