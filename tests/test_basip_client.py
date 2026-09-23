"""
Unit and integration tests for BAS-IP AA-14FB client, 38 panels topology, and access rules.
"""
import pytest
from basip.client import BASIPClient, BASIPManager
from basip.mock_panel import MockBASIPServer
from basip.models import BASIPPanelConfig, AccessCodeUser
from basip.topology import (
    generate_default_38_panels,
    load_panels_from_yaml,
    load_panels_from_csv,
    save_panels_to_csv,
)


@pytest.fixture(scope="module")
def mock_server():
    server = MockBASIPServer(host="127.0.0.1", port=18081)
    server.start()
    yield server
    server.stop()


@pytest.fixture
def client(mock_server):
    config = BASIPPanelConfig(
        panel_id="panel_test",
        name="Тестовая панель",
        host="127.0.0.1",
        port=18081,
        username="admin",
        password="123456",
        api_version="v1",
    )
    return BASIPClient(config)


def test_auth_and_connection_check(client):
    assert client.check_connection() is True


def test_create_and_get_identifier(client):
    ident = client.create_identifier(code="582910", name="Тестовый Жилец", lock_number=1)
    assert ident.identifier_number == "582910"
    assert ident.name == "Тестовый Жилец"
    assert ident.item_uid is not None

    all_ids = client.get_identifiers()
    found = [i for i in all_ids if i.identifier_number == "582910"]
    assert len(found) == 1
    assert found[0].name == "Тестовый Жилец"


def test_update_identifier(client):
    found = client.find_code_identifier(name="Тестовый Жилец")
    assert found is not None
    assert found.item_uid is not None

    ok = client.update_identifier(item_uid=found.item_uid, new_code="998877", name="Тестовый Жилец")
    assert ok is True

    updated = client.find_code_identifier(name="Тестовый Жилец")
    assert updated is not None
    assert updated.identifier_number == "998877"


def test_delete_identifier(client):
    found = client.find_code_identifier(name="Тестовый Жилец")
    assert found is not None
    assert found.item_uid is not None

    ok = client.delete_identifier(found.item_uid)
    assert ok is True

    after_delete = client.find_code_identifier(name="Тестовый Жилец")
    assert after_delete is None


def test_generate_38_panels_topology():
    """Verify that facility topology generates exactly 38 panels according to specification."""
    panels = generate_default_38_panels()
    assert len(panels) == 38

    # 2 gates
    gates = [p for p in panels if p.is_gate]
    assert len(gates) == 2
    assert gates[0].panel_id == "gate_1"
    assert gates[1].panel_id == "gate_2"

    # House 1: 3 double entrances = 6 panels
    h1 = [p for p in panels if p.building == 1]
    assert len(h1) == 6
    assert {p.entrance for p in h1} == {1, 2, 3}

    # House 2: 6 double entrances = 12 panels
    h2 = [p for p in panels if p.building == 2]
    assert len(h2) == 12
    assert {p.entrance for p in h2} == {1, 2, 3, 4, 5, 6}

    # House 3: 6 double entrances = 12 panels
    h3 = [p for p in panels if p.building == 3]
    assert len(h3) == 12
    assert {p.entrance for p in h3} == {1, 2, 3, 4, 5, 6}

    # House 4: 3 double entrances = 6 panels
    h4 = [p for p in panels if p.building == 4]
    assert len(h4) == 6
    assert {p.entrance for p in h4} == {1, 2, 3}


def test_user_panel_access_rules():
    """Verify that users are granted access to the correct panels and always to gates."""
    panels = generate_default_38_panels()
    manager = BASIPManager(panels)

    # User in House 1, Entrance 1: must get 2 gates + 2 doors of entrance 1 = 4 panels
    u1 = AccessCodeUser(
        row_index=2,
        user_id="101",
        name="Жилец 1-1",
        email="u1@test.com",
        house="1",
        entrance="1",
    )
    target1 = manager.get_target_panels_for_user(u1)
    assert len(target1) == 4
    assert any(p.panel_id == "gate_1" for p in target1)
    assert any(p.panel_id == "gate_2" for p in target1)
    assert any(p.panel_id == "d1_p1_a" for p in target1)
    assert any(p.panel_id == "d1_p1_b" for p in target1)
    assert not any(p.building == 2 for p in target1)

    # User in House 2, Entrance 5: 2 gates + 2 doors = 4 panels
    u2 = AccessCodeUser(
        row_index=3,
        user_id="102",
        name="Жилец 2-5",
        email="u2@test.com",
        house="2",
        entrance="5",
    )
    target2 = manager.get_target_panels_for_user(u2)
    assert len(target2) == 4
    assert any(p.panel_id == "d2_p5_a" for p in target2)
    assert any(p.panel_id == "d2_p5_b" for p in target2)

    # Security user with access to 'Все'
    u_admin = AccessCodeUser(
        row_index=4,
        user_id="104",
        name="Охрана",
        email="admin@test.com",
        house="Все",
        entrance="Все",
    )
    target_admin = manager.get_target_panels_for_user(u_admin)
    assert len(target_admin) == 38


def test_yaml_and_csv_panel_loading(tmp_path):
    """Test loading and saving panels from YAML and CSV files."""
    # Test loading pre-made panels.yaml
    panels_yaml = load_panels_from_yaml("panels.yaml")
    assert len(panels_yaml) == 38
    assert panels_yaml[0].panel_id == "gate_1"
    assert panels_yaml[0].is_gate is True

    # Test saving to CSV and loading back
    csv_file = tmp_path / "test_panels.csv"
    save_panels_to_csv(panels_yaml, str(csv_file))
    loaded_csv = load_panels_from_csv(str(csv_file))
    assert len(loaded_csv) == 38
    assert loaded_csv[0].panel_id == "gate_1"
    assert loaded_csv[0].is_gate is True
    assert loaded_csv[2].panel_id == "d1_p1_a"
    assert loaded_csv[2].building == 1
    assert loaded_csv[2].entrance == 1

