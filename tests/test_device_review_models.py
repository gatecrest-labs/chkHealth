from app.device_version_cache import _flush, _record, device_units
from app.routes.device_review_routes import _device_row


def _cluster(n_members, hardware="6200"):
    return {
        "name": "cl1",
        "hardware": hardware,
        "version": "R82",
        "cluster-members": [{"name": f"m{i}"} for i in range(n_members)],
    }


def test_gateway_is_one_device():
    assert device_units({"name": "gw"}, "Gateway") == 1


def test_cluster_counts_each_member():
    assert device_units(_cluster(2), "Cluster") == 2
    assert device_units(_cluster(3), "Cluster") == 3


def test_cluster_without_member_list_assumed_pair():
    assert device_units({"name": "cl"}, "Cluster") == 2
    assert device_units({"name": "cl", "cluster-members": None}, "Cluster") == 2


def test_device_row_exposes_units_and_hardware():
    row = _device_row(_cluster(2, "Check Point 6200"), "Cluster")
    assert row["units"] == 2
    assert row["hardware"] == "Check Point 6200"
    assert _device_row({"name": "gw", "hardware": "5000"}, "Gateway")["units"] == 1


def test_record_stores_hardware_and_units():
    vd: dict = {}
    _record(_cluster(2), "Cluster", "dom", vd)
    _record({"name": "gw", "version": "R81.20"}, "Gateway", "dom", vd)
    cl = vd["R82"][0]
    assert cl["hardware"] == "6200" and cl["units"] == 2
    gw = vd["R81.20"][0]
    assert gw["hardware"] == "" and gw["units"] == 1


def test_flush_keeps_model_fields_in_cached_devices():
    from app import device_version_cache as dvc

    vd: dict = {}
    _record(_cluster(2), "Cluster", "dom", vd)
    _flush(vd, total=1, domain_count=1, domains_ok=1, final=True)
    dev = dvc.get_device_versions()["by_version"][0]["devices"][0]
    assert dev["units"] == 2 and dev["hardware"] == "6200"
