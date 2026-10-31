from app.services.auth_service import verify_campus_domain


def test_campus_domain_exact_match():
    allowed = ["ui.ac.id", "ugm.ac.id", "itb.ac.id"]
    assert verify_campus_domain("andi@ui.ac.id", allowed) is True
    assert verify_campus_domain("budi@ugm.ac.id", allowed) is True
    assert verify_campus_domain("cici@itb.ac.id", allowed) is True


def test_campus_domain_subdomain_dot_boundary():
    allowed = ["ui.ac.id"]
    assert verify_campus_domain("student@cs.ui.ac.id", allowed) is True
    assert verify_campus_domain("mahasiswa@fk.ui.ac.id", allowed) is True
    assert verify_campus_domain("lab@comp.sci.ui.ac.id", allowed) is True


def test_campus_domain_rejection_of_spoofing():
    allowed = ["ui.ac.id"]
    # Prefix spoofing (e.g. evil-ui.ac.id, fakeui.ac.id or badui.ac.id)
    assert verify_campus_domain("attacker@evil-ui.ac.id", allowed) is False
    assert verify_campus_domain("attacker@fakeui.ac.id", allowed) is False
    assert verify_campus_domain("attacker@notui.ac.id", allowed) is False
    # Suffix spoofing (e.g. ui.ac.id.evil.com)
    assert verify_campus_domain("attacker@ui.ac.id.evil.com", allowed) is False
    assert verify_campus_domain("attacker@csui.ac.id", allowed) is False


def test_non_campus_domain():
    allowed = ["ui.ac.id", "ugm.ac.id"]
    assert verify_campus_domain("regular@gmail.com", allowed) is False
    assert verify_campus_domain("someone@yahoo.com", allowed) is False
