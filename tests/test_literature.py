"""Reference verification with a fake HTTP fetcher. The references below are TEST FIXTURES:
their titles/DOIs are deliberately artificial and are never treated as real literature."""

import json

import pytest

from regor import literature as lit
from regor.errors import ConfigError, ResearchError

FAKE_DOI = "10.0000/fixture.0001"


def crossref_payload(title, year, family):
    return json.dumps({"message": {"title": [title], "issued": {"date-parts": [[year]]},
                                   "author": [{"family": family, "given": "A"}],
                                   "container-title": ["Fixture Journal"]}})


def fetcher_for(table):
    def fetch(url):
        for k, v in table.items():
            if k in url:
                return v
        return 404, ""
    return fetch


def _add(proj, key="fix2020", **kw):
    return lit.add(proj, {"key": key, "title": "A Fixture Study of Things", "authors": ["Doe, Jane"],
                          "year": 2020, "doi": FAKE_DOI, **kw})


def test_verified_when_metadata_matches(proj):
    _add(proj)
    f = fetcher_for({"api.crossref.org": (200, crossref_payload("A fixture study of things", 2020, "Doe"))})
    v = lit.verify(proj, "fix2020", fetch=f)
    assert v["status"] == "verified" and v["method"] == "crossref"


def test_mismatch_fails(proj):
    _add(proj)
    f = fetcher_for({"api.crossref.org": (200, crossref_payload("Something Else Entirely", 2018, "Roe"))})
    v = lit.verify(proj, "fix2020", fetch=f)
    assert v["status"] == "failed" and len(v["mismatches"]) == 3


def test_nonexistent_identifier_fails(proj):
    _add(proj)
    v = lit.verify(proj, "fix2020", fetch=fetcher_for({}))
    assert v["status"] == "failed" and "not found" in v["note"]


def test_network_error_stays_unverified(proj):
    _add(proj)

    def boom(url):
        raise ResearchError("offline")
    v = lit.verify(proj, "fix2020", fetch=boom)
    assert v["status"] == "unverified" and "could not reach" in v["note"]


def test_no_identifier_needs_manual(proj):
    lit.add(proj, {"key": "noid", "title": "Fixture without identifier"})
    v = lit.verify(proj, "noid", fetch=fetcher_for({}))
    assert v["status"] == "unverified" and "manually" in v["note"]
    with pytest.raises(ConfigError):
        lit.verify_manual(proj, "noid", "", "")
    assert lit.verify_manual(proj, "noid", "https://example.invalid/record", "Dr Test")["status"] == "verified"


def test_arxiv_path(proj):
    lit.add(proj, {"key": "ax", "title": "Fixture Preprint", "authors": ["Smith, Al"], "year": 2021,
                   "arxiv": "0000.00000"})
    atom = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Fixture Preprint</title>'
            '<published>2021-01-01T00:00:00Z</published><author><name>Al Smith</name></author></entry></feed>')
    v = lit.verify(proj, "ax", fetch=fetcher_for({"export.arxiv.org": (200, atom)}))
    assert v["status"] == "verified" and v["method"] == "arxiv"


def test_bibtex_roundtrip_exports_verified_only(proj):
    bib = ("@article{fixA,\n  title = {Fixture A},\n  author = {Doe, Jane and Roe, Rick},\n  year = {2019},\n"
           "  journal = {Fixture Journal},\n  doi = {10.0000/fixture.a}\n}\n"
           "@inproceedings{fixB,\n  title = {Fixture B},\n  author = {Poe, P},\n  year = 2020\n}\n")
    assert lit.import_bibtex(proj, bib) == ["fixA", "fixB"]
    lit.verify_manual(proj, "fixA", "https://example.invalid/a", "Dr Test")
    ok, total = lit.export_bibtex(proj)
    text = (proj.root / "literature" / "references.bib").read_text()
    assert (ok, total) == (1, 2) and "fixA" in text and "fixB" not in text
    assert lit.write_matrix(proj) == 2
    review = lit.review_skeleton(proj)
    assert "[@fixA]" in review and "fixB: Fixture B [REFERENCE NOT VERIFIED]" in review


def test_bad_key_rejected(proj):
    with pytest.raises(ConfigError):
        lit.add(proj, {"key": "1bad key", "title": "x"})
