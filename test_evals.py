#!/usr/bin/env python3
"""자가 검증. 프레임워크 없이 assert 만 사용한다. 실행: python3 test_evals.py"""
import json, os, sqlite3, sys, tempfile

os.environ.setdefault("EVALS_DB", os.path.join(tempfile.mkdtemp(), "t.db"))
import evals as E

CHECKS = []
def check(fn):
    CHECKS.append(fn); return fn


# ---- 1단위: 정규화 / 멱등성 -------------------------------------------------
@check
def test_canonical_url():
    assert E.canonical_url("https://WWW.Example.com/a/b/?utm_source=x&id=3#frag") == "https://example.com/a/b?id=3"
    assert E.canonical_url("https://arxiv.org/abs/2608.24040v1") == E.canonical_url("http://arxiv.org/abs/2608.24040")
    assert E.canonical_url("https://a.com/") == "https://a.com/"

@check
def test_hash_and_similarity():
    h1 = E.content_hash("Demystifying Evals", "x" * 200)
    h2 = E.content_hash("demystifying   evals!", "x" * 200)
    assert h1 == h2, "제목 정규화 후 같은 해시여야 한다"
    assert E.content_hash("Other", "x" * 200) != h1
    assert E.title_similarity("agent evals benchmark", "agent evals benchmark") == 1.0
    assert E.title_similarity("RAG evaluation model", "hardware design agents") < 0.2

# ---- 1단위: 관련성 정책 ------------------------------------------------------
@check
def test_assess_high():
    a = E.assess("Demystifying evals for AI agents",
                 "This post explains how to evaluate LLM agents with graders, trajectory inspection, "
                 "and a repeatable evaluation harness for regression testing in production." * 2)
    assert a["eligibility"] == "high", a
    assert a["score"] >= 70 and a["confidence"] > 40
    assert "agent-evals" in a["topics"] and "grading" in a["topics"]
    assert any("evals:" in e for e in a["evidence"])

@check
def test_assess_low_without_ai_context():
    a = E.assess("A new benchmark for concrete strength testing",
                 "We present a materials benchmark and evaluation protocol for concrete mixtures. " * 3)
    assert a["eligibility"] == "low", a  # AI 맥락 없음

@check
def test_assess_short_excerpt_penalised():
    long = E.assess("LLM agent evaluation benchmark", "evaluating llm agent benchmark grading " * 5)
    short = E.assess("LLM agent evaluation benchmark", "too short")
    assert short["score"] < long["score"]
    assert any("100자 미만" in e for e in short["evidence"])

# ---- 스키마 / 출처 시딩 -------------------------------------------------------
@check
def test_schema_and_seed_does_not_reenable():
    con = E.connect(os.environ["EVALS_DB"])
    E.seed_sources(con)
    n = con.execute("SELECT COUNT(*) c FROM sources").fetchone()["c"]
    assert n == len(E.DEFAULT_SOURCES)
    con.execute("UPDATE sources SET enabled=0 WHERE name=?", (E.DEFAULT_SOURCES[0][0],))
    con.commit()
    E.seed_sources(con)  # 재시딩
    off = con.execute("SELECT enabled FROM sources WHERE name=?", (E.DEFAULT_SOURCES[0][0],)).fetchone()["enabled"]
    assert off == 0, "운영자가 끈 피드가 재시딩으로 다시 켜지면 안 된다"
    assert con.execute("SELECT COUNT(*) c FROM sources").fetchone()["c"] == n
    con.close()

@check
def test_unique_indexes_block_duplicates():
    con = E.connect(os.environ["EVALS_DB"])
    row = ("t", "https://x.com/a", "https://x.com/a", "hash-1", None, "e", "new", "", E.now())
    con.execute("INSERT INTO items(title,url,canonical_url,content_hash,published,excerpt,gate,gate_reason,collected_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)", row)
    con.commit()
    for dup, label in ((row, "동일 URL"), (("t2", "https://x.com/b", "https://x.com/b", "hash-1", None, "e", "new", "", E.now()), "동일 해시")):
        try:
            con.execute("INSERT INTO items(title,url,canonical_url,content_hash,published,excerpt,gate,gate_reason,collected_at)"
                        " VALUES(?,?,?,?,?,?,?,?,?)", dup)
            raise AssertionError(f"{label} 중복이 삽입되었다")
        except sqlite3.IntegrityError:
            con.rollback()
    con.close()





# ---- 2단위 진입 전: 파서 / 게이트 -------------------------------------------
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Feed</title>
<item><title>Evaluating LLM agents at scale</title><link>https://aws.amazon.com/blogs/machine-learning/x</link>
<description>&lt;p&gt;A benchmark and evaluation harness for LLM agent tool-use with graders and trajectory review in production regression testing pipelines.&lt;/p&gt;</description>
<pubDate>Mon, 01 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Agent trajectory benchmark for tool-use evaluation</title>
<link rel="alternate" href="http://arxiv.org/abs/2609.00001v1"/>
<summary>We introduce a benchmark that evaluates LLM agent trajectories, grading tool calls against ground truth with a reproducible evaluation harness.</summary>
<published>2026-09-01T00:00:00Z</published></entry></feed>"""

@check
def test_parse_rss_and_atom():
    r = E.parse_feed(RSS)[0]
    assert r["title"] == "Evaluating LLM agents at scale"
    assert r["url"].startswith("https://aws.amazon.com")
    assert "<p>" not in r["excerpt"] and "benchmark" in r["excerpt"]
    a = E.parse_feed(ATOM)[0]
    assert a["url"] == "http://arxiv.org/abs/2609.00001v1"
    assert len(a["excerpt"]) > E.MIN_EXCERPT

@check
def test_ssrf_allowlist():
    for bad in ("http://169.254.169.254/latest/meta-data/", "file:///etc/passwd", "https://evil.example.com/f.xml"):
        try:
            E.fetch(bad)
            raise AssertionError(f"허용되지 않은 주소를 가져왔다: {bad}")
        except ValueError:
            pass

@check
def test_gate_pipeline():
    db = os.path.join(tempfile.mkdtemp(), "g.db")
    con = E.connect(db); E.seed_sources(con)
    c = E.parse_feed(ATOM)[0]
    assert E.gate_candidate(con, c)[0] == "new"
    con.execute("INSERT INTO items(title,url,canonical_url,content_hash,excerpt,gate,gate_reason,collected_at)"
                " VALUES(?,?,?,?,?,'new','',?)",
                (c["title"], c["url"], E.canonical_url(c["url"]), E.content_hash(c["title"], c["excerpt"]),
                 c["excerpt"], E.now()))
    con.commit()
    # 같은 논문의 https + v2 판본 -> URL 중복
    dup = dict(c, url="https://arxiv.org/abs/2609.00001v2")
    assert E.gate_candidate(con, dup)[0] == "dup_url"
    # 제목만 살짝 다른 자료 -> 유사 중복
    near = dict(c, url="https://huggingface.co/blog/other",
                title="Agent trajectory benchmark for tool-use evaluation study")
    assert E.gate_candidate(con, near)[0] == "dup_similar"
    # 짧은 발췌문
    assert E.gate_candidate(con, {"title": "New LLM eval", "url": "https://huggingface.co/blog/s", "excerpt": "short"})[0] == "short_excerpt"
    # 무관 자료
    assert E.gate_candidate(con, {"title": "Concrete mixture strength study", "url": "https://huggingface.co/blog/c",
                                  "excerpt": "We measure compressive strength of concrete samples over 28 days. " * 4})[0] == "low_relevance"
    con.close()

@check
def test_priority_needs_min_samples_and_is_capped():
    db = os.path.join(tempfile.mkdtemp(), "p.db")
    con = E.connect(db); E.seed_sources(con)
    sid = con.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
    a = {"score": 60, "topics": ["rag"]}
    def add(i, decision):
        con.execute("INSERT INTO items(source_id,title,url,canonical_url,content_hash,excerpt,gate,gate_reason,collected_at)"
                    " VALUES(?,?,?,?,?,'','new','',?)", (sid, f"t{i}", f"u{i}", f"u{i}", f"h{i}", E.now()))
        iid = con.execute("SELECT last_insert_rowid() r").fetchone()["r"]
        con.execute("INSERT INTO assessments(item_id,score,confidence,eligibility,topics,policy_version,created_at)"
                    " VALUES(?,50,50,'high','[\"rag\"]',?,?)", (iid, E.POLICY_VERSION, E.now()))
        con.execute("INSERT INTO feedback(item_id,decision,created_at) VALUES(?,?,?)", (iid, decision, E.now()))
        con.commit()
        return iid
    probe = add(0, "held")
    assert E.priority_for(con, probe, a) == 60, "표본 부족 시 보정 없음"
    for i in range(1, 9):
        add(i, "accepted")
    p = E.priority_for(con, probe, a)
    assert 60 < p <= 60 + 2 * E.WEIGHT_CAP, p
    con.close()


# ---- 발췌문 보강 ------------------------------------------------------------
@check
def test_extract_excerpt_prefers_meta():
    html = ("<html><head><script>var x='<p>fake</p>';</script>"
            "<meta property=\"og:description\" content=\"" + "LLM 벤치마크가 실제로 무엇을 측정하는지 분석한다. " * 4 + "\">"
            "</head><body><p>short</p></body></html>")
    out = E.extract_excerpt(html)
    assert out.startswith("LLM 벤치마크가"), out[:60]
    assert "fake" not in out and "<" not in out

@check
def test_extract_excerpt_falls_back_to_paragraphs():
    html = "<html><body><p>x</p>" + "".join(
        f"<p>문단 {i}: 평가 하네스와 채점기의 차이를 설명하는 충분히 긴 본문입니다.</p>" for i in range(3)) + "</body></html>"
    out = E.extract_excerpt(html)
    assert len(out) >= E.MIN_EXCERPT and "문단 0" in out and "<p>" not in out

@check
def test_enrich_skips_when_excerpt_is_enough():
    cand = {"title": "t", "url": "https://blocked.example.com/x", "excerpt": "a" * 200}
    assert E.enrich_excerpt(cand) is cand, "충분한 발췌문에 네트워크를 쓰면 안 된다"

@check
def test_enrich_survives_fetch_failure():
    cand = {"title": "t", "url": "https://evil.example.com/x", "excerpt": "short"}
    assert E.enrich_excerpt(cand)["excerpt"] == "short", "실패해도 후보를 잃지 않아야 한다"


# ---- 2단위: 학습 콘텐츠 ------------------------------------------------------
GOOD = {"summary": "요약", "practical": "실무", "terms": [{"term": "t", "definition": "d"}],
        "points": ["p1"], "difficulty": "advanced"}

@check
def test_validate_note_rejects_broken_output():
    assert E.validate_note(dict(GOOD))["difficulty"] == "advanced"
    assert E.validate_note(dict(GOOD, difficulty="아무거나"))["difficulty"] == "intermediate"
    for bad in ({}, dict(GOOD, points=[]), dict(GOOD, terms="문자열"), dict(GOOD, summary="  "), "문자열"):
        try:
            E.validate_note(bad)
            raise AssertionError(f"잘못된 출력을 통과시켰다: {bad}")
        except (ValueError, AttributeError, TypeError):
            pass
    # 형식이 어긋난 항목은 조용히 버려지되 노트는 살아남는다
    mixed = E.validate_note(dict(GOOD, terms=[{"term": "t", "definition": "d"}, {"term": ""}, "x"], points=["p", "", 3]))
    assert len(mixed["terms"]) == 1 and mixed["points"] == ["p"]

@check
def test_build_note_falls_back_and_records_reason(monkey=None):
    orig = E.llm_note
    E.llm_note = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("API 없음"))
    try:
        n = E.build_note("Agent evals benchmark", "본문", ["trajectory"])
    finally:
        E.llm_note = orig
    assert n["generator"] == "fallback"
    assert n["warnings"] and "RuntimeError" in n["warnings"][0]
    assert n["difficulty"] == "advanced", "태그 기반 난이도가 반영돼야 한다"
    assert E.build_note("t", "본문", [], use_llm=False)["warnings"], "결정적 노트에도 경고를 남긴다"

@check
def test_generate_respects_budget_and_order():
    db = os.path.join(tempfile.mkdtemp(), "n.db")
    con = E.connect(db)
    calls = []
    orig = E.llm_note
    E.llm_note = lambda title, excerpt: (calls.append(title), dict(GOOD, generator="llm:test", warnings=[]))[1]
    try:
        for i, (elig, prio) in enumerate([("medium", 50), ("high", 90), ("high", 95)]):
            con.execute("INSERT INTO items(title,url,canonical_url,content_hash,excerpt,gate,gate_reason,collected_at)"
                        " VALUES(?,?,?,?,'본문','new','',?)", (f"item{i}", f"u{i}", f"u{i}", f"h{i}", E.now()))
            iid = con.execute("SELECT last_insert_rowid() r").fetchone()["r"]
            con.execute("INSERT INTO assessments(item_id,score,confidence,eligibility,topics,priority,policy_version,created_at)"
                        " VALUES(?,?,80,?,'[\"rag\"]',?,?,?)", (iid, prio, elig, prio, E.POLICY_VERSION, E.now()))
        con.commit()
        stats = E.generate(con, budget=2)
    finally:
        E.llm_note = orig
    assert stats == {"generated": 3, "llm": 2, "fallback": 1, "fulltext": 0, "regenerated": 0}, stats
    assert calls == ["item2", "item1"], f"high·우선순위 순서가 아니다: {calls}"
    assert con.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"] == 3
    assert E.generate(con, budget=0)["generated"] == 0, "예산이 없으면 fallback 을 또 fallback 으로 덮지 않는다"
    con.close()


@check
def test_generate_replaces_fallback_when_budget_frees_up():
    """예산 소진으로 fallback 이 된 노트는 다음 실행에서 LLM 판으로 교체된다. 단 사람이 수용한 건 건드리지 않는다."""
    db = os.path.join(tempfile.mkdtemp(), "n.db")
    con = E.connect(db)
    orig = E.llm_note
    E.llm_note = lambda title, excerpt: dict(GOOD, generator="llm:test", warnings=[])
    try:
        for i in range(2):
            con.execute("INSERT INTO items(title,url,canonical_url,content_hash,excerpt,gate,gate_reason,collected_at)"
                        " VALUES(?,?,?,?,'본문','new','',?)", (f"item{i}", f"u{i}", f"u{i}", f"h{i}", E.now()))
            iid = con.execute("SELECT last_insert_rowid() r").fetchone()["r"]
            con.execute("INSERT INTO assessments(item_id,score,confidence,eligibility,topics,priority,policy_version,created_at)"
                        " VALUES(?,50,80,'high','[\"rag\"]',50,?,?)", (iid, E.POLICY_VERSION, E.now()))
        con.commit()
        assert E.generate(con, budget=0) == {"generated": 2, "llm": 0, "fallback": 2, "fulltext": 0, "regenerated": 0}

        # 하나는 사람이 수용 → 확정본이므로 교체 대상에서 빠진다
        kept = con.execute("SELECT item_id FROM notes ORDER BY id LIMIT 1").fetchone()["item_id"]
        con.execute("INSERT INTO feedback(item_id,decision,reviewer,created_at) VALUES(?,'accepted','me',?)",
                    (kept, E.now()))
        con.commit()

        stats = E.generate(con, budget=8)
    finally:
        E.llm_note = orig
    assert stats["regenerated"] == 1 and stats["llm"] == 1, stats
    gens = dict(con.execute("SELECT item_id, generator FROM notes").fetchall())
    assert gens[kept] == "fallback", "사람이 수용한 노트를 덮어썼다"
    assert con.execute("SELECT COUNT(*) c FROM notes WHERE generator='llm:test'").fetchone()["c"] == 1
    assert con.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"] == 2, "교체인데 노트가 늘었다"
    con.close()


# ---- 3단위: 검토 큐 / 판정 ---------------------------------------------------
def _fixture():
    db = os.path.join(tempfile.mkdtemp(), "r.db")
    con = E.connect(db); E.seed_sources(con)
    sid = con.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
    ids = []
    for i, (gate, elig, prio) in enumerate([("new", "high", 90), ("new", "medium", 60), ("low_relevance", "low", 10)]):
        con.execute("INSERT INTO items(source_id,title,url,canonical_url,content_hash,excerpt,gate,gate_reason,"
                    "published,collected_at) VALUES(?,?,?,?,?,?,?,'',?,?)",
                    (sid, f"item{i}", f"https://x/{i}", f"https://x/{i}", f"h{i}", "발췌 " * 30, gate,
                     "2026-09-01", E.now()))
        iid = con.execute("SELECT last_insert_rowid() r").fetchone()["r"]; ids.append(iid)
        con.execute("INSERT INTO assessments(item_id,score,confidence,eligibility,evidence,topics,priority,"
                    "policy_version,created_at) VALUES(?,?,80,?,'[\"evals:x\"]','[\"rag\"]',?,?,?)",
                    (iid, prio, elig, prio, E.POLICY_VERSION, E.now()))
    con.execute("INSERT INTO notes(item_id,summary,practical,terms,points,difficulty,generator,warnings,created_at)"
                " VALUES(?,'요약','실무','[]','[\"p\"]','beginner','fallback','[]',?)", (ids[0], E.now()))
    con.commit()
    return con, ids

@check
def test_queue_orders_and_shapes():
    con, ids = _fixture()
    q = E.queue_payload(con, "pending")
    assert [i["id"] for i in q["items"]] == [ids[0], ids[1]], "우선순위 내림차순이어야 한다"
    assert q["counts"]["pending"] == 2
    assert q["items"][0]["note"]["summary"] == "요약" and q["items"][1]["note"] is None
    assert q["items"][0]["evidence"] == ["evals:x"] and q["items"][0]["topics"] == ["rag"]
    assert [i["id"] for i in E.queue_payload(con, "low")["items"]] == [ids[2]]
    con.close()

@check
def test_decision_persists_and_leaves_queue():
    con, ids = _fixture()
    E.record_decision(con, {"item_id": ids[0], "decision": "accepted", "reason": "근거 충분"})
    q = E.queue_payload(con, "pending")
    assert [i["id"] for i in q["items"]] == [ids[1]], "판정한 자료는 대기열에서 빠져야 한다"
    assert q["counts"]["accepted"] == 1
    assert E.queue_payload(con, "decided")["items"][0]["decision"] == "accepted"
    con.close()

@check
def test_edits_applied_only_on_accepted_with_edits():
    con, ids = _fixture()
    E.record_decision(con, {"item_id": ids[0], "decision": "accepted", "corrected_topics": ["safety"],
                            "corrected_difficulty": "advanced"})
    row = con.execute("SELECT topics FROM assessments WHERE item_id=?", (ids[0],)).fetchone()
    assert row["topics"] == '["rag"]', "단순 수용은 판정 근거를 덮어쓰면 안 된다"
    E.record_decision(con, {"item_id": ids[0], "decision": "accepted_with_edits",
                            "corrected_topics": ["safety"], "corrected_difficulty": "advanced"})
    assert con.execute("SELECT topics FROM assessments WHERE item_id=?", (ids[0],)).fetchone()["topics"] == '["safety"]'
    assert con.execute("SELECT difficulty FROM notes WHERE item_id=?", (ids[0],)).fetchone()["difficulty"] == "advanced"
    assert con.execute("SELECT COUNT(*) c FROM feedback WHERE item_id=?", (ids[0],)).fetchone()["c"] == 2, "판정 이력은 보존"
    con.close()

@check
def test_decision_rejects_bad_input():
    con, ids = _fixture()
    for bad in ({"item_id": ids[0], "decision": "삭제"}, {"item_id": 99999, "decision": "accepted"},
                {"decision": "accepted"}):
        try:
            E.record_decision(con, bad)
            raise AssertionError(f"잘못된 입력을 받아들였다: {bad}")
        except ValueError:
            pass
    E.record_decision(con, {"item_id": ids[0], "decision": "accepted_with_edits",
                            "corrected_topics": ["ok", 3, None], "corrected_difficulty": "초급"})
    f = con.execute("SELECT corrected_topics t, corrected_difficulty d FROM feedback").fetchone()
    assert json.loads(f["t"]) == ["ok"] and f["d"] is None, "형식이 어긋난 수정값은 버려야 한다"
    con.close()

@check
def test_server_blocks_non_local_host():
    import http.client, threading, socket
    con = _fixture()[0]
    E.ReviewHandler.db_path = con.execute("PRAGMA database_list").fetchone()[2]
    con.close()
    srv = E.ThreadingHTTPServer(("127.0.0.1", 0), E.ReviewHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        def call(method, path, host, body=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                c.request(method, path, body=body, headers={"Host": host, "Content-Type": "application/json"})
                r = c.getresponse(); r.read()          # 본문을 읽고 닫아야 서버가 reset 을 보지 않는다
                return r.status
            finally:
                c.close()
        assert call("GET", "/api/queue", "localhost") == 200
        assert call("POST", "/api/decide", "attacker.example.com", '{"decision":"accepted"}') == 403, \
            "외부 Host 헤더로 판정을 바꿀 수 있으면 안 된다"
        assert call("POST", "/api/decide", "127.0.0.1", "not json") == 400
    finally:
        srv.shutdown()


# ---- 내보내기 / 운영 보고 ----------------------------------------------------
def _accepted_fixture():
    con, ids = _fixture()
    con.execute("INSERT INTO notes(item_id,summary,practical,terms,points,difficulty,generator,warnings,created_at)"
                " VALUES(?,'요약2','실무2','[{\"term\":\"T\",\"definition\":\"D\"}]','[\"p2\"]',"
                "'intermediate','llm:test','[]',?)", (ids[1], E.now()))
    con.execute("INSERT INTO runs(started_at,status,stats) VALUES(?,'ok',?)",
                (E.now(), json.dumps({"candidates": 48, "dup_url": 3, "dup_similar": 1,
                                      "low_relevance": 12, "short_excerpt": 0, "feed_failures": 0, "errors": []})))
    con.commit()
    for i in ids[:2]:
        E.record_decision(con, {"item_id": i, "decision": "accepted"})
    return con, ids

@check
def test_export_writes_once_and_is_idempotent():
    con, ids = _accepted_fixture()
    vault = tempfile.mkdtemp()
    r1 = E.export(con, vault)
    assert r1["written"] == 2 and os.path.exists(r1["path"])
    body = open(r1["path"], encoding="utf-8").read()
    for must in ("# AI Evals 학습 업데이트", "**이번 업데이트:** 신규 자료 2건", "### 핵심 요약", "### 판정 근거",
                 "## 수집·검토 기록", "| 검색 후보 | 48 |", "| 신규 학습자료 수용 | 2 |", "논리 저장 경로"):
        assert must in body, f"내보낸 문서에 '{must}' 가 없다"
    assert "| 용어 | 쉬운 정의 |" in body and "| T | D |" in body
    assert not any(f.endswith(".tmp") for f in os.listdir(vault)), "임시 파일이 남았다"
    r2 = E.export(con, vault)
    assert r2["written"] == 0, "같은 자료를 두 번 내보내면 안 된다"
    assert len(os.listdir(vault)) == 1
    con.close()

@check
def test_export_links_only_accepted_related():
    con, ids = _accepted_fixture()
    rel = E.related_items(con, ids[0], "item0", ["rag"])
    assert [x["title"] for x in rel] == ["item1"], rel
    assert rel[0]["shared"] == ["rag"] and 0 < rel[0]["similarity"] <= 100
    # 수용되지 않은 자료(ids[2], low)는 연결 대상이 아니다
    assert all(x["title"] != "item2" for x in rel)
    con.close()

@check
def test_export_skips_items_without_notes():
    con, ids = _fixture()
    con.execute("INSERT INTO runs(started_at,status,stats) VALUES(?,'ok','{}')", (E.now(),))
    con.commit()
    E.record_decision(con, {"item_id": ids[1], "decision": "accepted"})   # 노트 없음
    assert E.export(con, tempfile.mkdtemp())["written"] == 0
    E.record_decision(con, {"item_id": ids[0], "decision": "accepted"})   # 노트 있음
    assert E.export(con, tempfile.mkdtemp())["written"] == 1
    con.close()

@check
def test_report_surfaces_alerts():
    con, ids = _accepted_fixture()
    out = E.report(con)
    assert "사람 수용 2건" in out
    assert "fallback" not in out, f"사람이 수용한 fallback 은 확정본이라 경보 대상이 아니다: {out}"
    con.execute("INSERT INTO notes(item_id,summary,practical,terms,points,difficulty,generator,warnings,created_at)"
                " VALUES(?,'요약3','실무3','[]','[]','intermediate','fallback','[]',?)", (ids[2], E.now()))
    con.commit()
    assert "미교체 fallback 노트 1건" in E.report(con), "수용되지 않은 fallback 은 경보로 떠야 한다"
    con.execute("UPDATE sources SET enabled=0, fail_streak=3 WHERE name=?", (E.DEFAULT_SOURCES[0][0],))
    con.commit()
    assert "연속 실패 3회" in E.report(con)
    con.close()

@check
def test_cli_commands_run():
    db = os.path.join(tempfile.mkdtemp(), "cli.db")
    for cmd in (["init"], ["report"], ["export", "--vault", tempfile.mkdtemp()]):
        assert E.main(cmd + ["--db", db]) == 0, cmd


@check
def test_atom_picks_alternate_link_not_self():
    feed = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>
    <title>Agent eval benchmark</title>
    <link rel="self" href="https://arxiv.org/WRONG"/>
    <link rel="alternate" href="https://arxiv.org/abs/2609.00002"/>
    <summary>We evaluate LLM agents with a grading harness over tool-use trajectories and report benchmark results.</summary>
    </entry></feed>"""
    assert E.parse_feed(feed)[0]["url"] == "https://arxiv.org/abs/2609.00002"


@check
def test_server_does_not_leak_connections():
    import http.client, threading, resource
    con, _ = _fixture()
    db = con.execute("PRAGMA database_list").fetchone()[2]
    con.close()
    E.ReviewHandler.db_path = db
    srv = E.ThreadingHTTPServer(("127.0.0.1", 0), E.ReviewHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    open_files = lambda: len(os.listdir("/dev/fd"))
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", "/api/queue", headers={"Host": "127.0.0.1"}); c.getresponse().read()
        before = open_files()
        for _ in range(25):
            c.request("GET", "/api/queue", headers={"Host": "127.0.0.1"}); c.getresponse().read()
        c.request("GET", "/nope", headers={"Host": "127.0.0.1", "Connection": "close"}); c.getresponse().read()
        c.close()
        assert open_files() <= before + 3, f"열린 파일이 {before} -> {open_files()} 로 늘었다 (연결 누수)"
    finally:
        srv.shutdown()


# ---- 공급자 레이어 (ollama / groq) -------------------------------------------
@check
def test_parse_note_strips_fences_and_think():
    body = json.dumps(GOOD, ensure_ascii=False)
    for raw in (body, f"```json\n{body}\n```", f"<think>고민중</think>\n{body}",
                f"여기 결과입니다:\n{body}\n감사합니다"):
        assert E.parse_note(raw)["summary"] == "요약", raw[:30]

@check
def test_provider_chain_falls_through_and_labels():
    calls = []
    orig, order = dict(E.BACKENDS), list(E.PROVIDERS)
    E.PROVIDERS[:] = ["ollama", "groq"]          # 기본 순서와 무관하게 검사한다
    E.BACKENDS["ollama"] = (lambda t, e: (calls.append("ollama"), (_ for _ in ()).throw(OSError("서버 꺼짐")))[0],
                            lambda: "m1")
    E.BACKENDS["groq"] = (lambda t, e: (calls.append("groq"), dict(GOOD))[1], lambda: "m2")
    try:
        n = E.llm_note("t", "본문")
        assert calls == ["ollama", "groq"], calls
        assert n["generator"] == "groq:m2"
        assert n["warnings"] and "ollama" in n["warnings"][0] and "서버 꺼짐" in n["warnings"][0]
        # 전부 실패하면 예외 -> build_note 가 결정적 fallback 으로 받는다
        E.BACKENDS["groq"] = (lambda t, e: (_ for _ in ()).throw(ValueError("키 없음")), lambda: "m2")
        note = E.build_note("t", "본문", ["rag"])
        assert note["generator"] == "fallback" and "키 없음" in note["warnings"][0]
    finally:
        E.BACKENDS.clear(); E.BACKENDS.update(orig); E.PROVIDERS[:] = order

@check
def test_groq_requires_key_without_network():
    saved = os.environ.pop("GROQ_API_KEY", None)
    try:
        E.note_groq("t", "본문")
        raise AssertionError("키 없이 호출이 진행되었다")
    except ValueError as exc:
        assert "GROQ_API_KEY" in str(exc)
    finally:
        if saved:
            os.environ["GROQ_API_KEY"] = saved

@check
def test_ollama_payload_shape():
    seen = {}
    orig = E.post_json
    E.post_json = lambda url, payload, headers=None, timeout=None: (
        seen.update(url=url, payload=payload), {"message": {"content": json.dumps(GOOD)}})[1]
    try:
        E.note_ollama("제목", "본문" * 5000)
    finally:
        E.post_json = orig
    assert seen["url"].endswith("/api/chat")
    assert seen["payload"]["format"]["required"] == list(E.REQUIRED_FIELDS), "JSON 스키마 강제가 빠졌다"
    assert seen["payload"]["stream"] is False and seen["payload"]["think"] is False
    user = seen["payload"]["messages"][1]["content"]
    assert "<source_text" in user, "원문 구획이 없다"
    assert len(user) < E.FULLTEXT_MAX + 500, f"길이 상한 미적용: {len(user)}"


@check
def test_validate_note_requires_korean_summary():
    english = dict(GOOD, summary="Amazon Bedrock AgentCore Evaluations is a framework-agnostic service.")
    try:
        E.validate_note(english)
        raise AssertionError("영어 요약이 통과되었다")
    except ValueError as exc:
        assert "한국어" in str(exc)
    # 한글이 섞인 정상 출력은 통과한다
    assert E.validate_note(dict(GOOD, summary="AgentCore Evaluations는 프레임워크 중립 평가 서비스입니다."))


# ---- 무료 한도(429) 처리 -----------------------------------------------------
class _FakeHTTPError(Exception):
    def __init__(self, code, headers, body):
        self.code, self.headers, self._body = code, headers, body.encode()
    def read(self, n=None):
        return self._body

@check
def test_429_short_wait_retries_once_then_succeeds():
    import urllib.error
    calls, slept = [], []
    orig_open, orig_sleep, orig_err = E.request.urlopen, E.time.sleep, E.error.HTTPError
    E.error.HTTPError = _FakeHTTPError
    E.time.sleep = lambda s: slept.append(s)
    class OK:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=None): return b'{"ok": true}'
    def fake(req, timeout=None):
        calls.append(1)
        if len(calls) == 1:
            raise _FakeHTTPError(429, {"retry-after": "2"}, '{"error":"rate limit"}')
        return OK()
    E.request.urlopen = fake
    try:
        assert E.post_json("https://x/y", {}) == {"ok": True}
        assert len(calls) == 2 and slept == [2.0], (calls, slept)
    finally:
        E.request.urlopen, E.time.sleep, E.error.HTTPError = orig_open, orig_sleep, orig_err

@check
def test_429_long_wait_fails_over_to_next_provider():
    calls, slept = [], []
    orig_open, orig_sleep, orig_err = E.request.urlopen, E.time.sleep, E.error.HTTPError
    E.error.HTTPError = _FakeHTTPError
    E.time.sleep = lambda s: slept.append(s)
    def fake(req, timeout=None):
        calls.append(1)
        raise _FakeHTTPError(429, {"retry-after": "600"}, "{}")
    E.request.urlopen = fake
    try:
        E.post_json("https://x/y", {})
        raise AssertionError("긴 대기에서 재시도를 계속했다")
    except ValueError as exc:
        assert "무료 한도 초과" in str(exc) and len(calls) == 1 and not slept, (calls, slept)
    finally:
        E.request.urlopen, E.time.sleep, E.error.HTTPError = orig_open, orig_sleep, orig_err

@check
def test_http_error_body_is_surfaced():
    orig_open, orig_err = E.request.urlopen, E.error.HTTPError
    E.error.HTTPError = _FakeHTTPError
    E.request.urlopen = lambda req, timeout=None: (_ for _ in ()).throw(
        _FakeHTTPError(403, {}, '{"error":{"message":"blocked by UA"}}'))
    try:
        E.post_json("https://x/y", {})
        raise AssertionError("403 이 통과했다")
    except ValueError as exc:
        assert "403" in str(exc) and "blocked by UA" in str(exc), "원인 메시지를 삼키면 안 된다"
    finally:
        E.request.urlopen, E.error.HTTPError = orig_open, orig_err


@check
def test_publish_date_normalized_across_feed_formats():
    assert E.normalize_date("Tue, 01 Sep 2026 19:12:43 +0000") == "2026-09-01", "RSS 날짜가 잘린다"
    assert E.normalize_date("2026-09-01T10:33:18Z") == "2026-09-01"
    assert E.normalize_date("") == "" and E.normalize_date("쓰레기값") == "쓰레기값"[:10]
    rss = E.parse_feed(RSS)[0]
    assert rss["published"] == "2026-09-01", rss["published"]
    assert E.parse_feed(ATOM)[0]["published"] == "2026-09-01"


@check
def test_clean_text_strips_latex_from_arxiv_abstracts():
    raw = ("We introduce \\textbf{S\\textsuperscript{3}Gym}, a benchmark. "
           "The \\emph{agent} scores $92\\%$ on \\texttt{tool-use} tasks.")
    out = E.clean_text(raw)
    assert "\\textbf" not in out and "\\emph" not in out and "$" not in out, out
    assert "S3Gym" in out and "agent" in out and "tool-use" in out, out
    # 평범한 텍스트는 건드리지 않는다
    assert E.clean_text("<p>A normal &nbsp; abstract.</p>") == "A normal abstract."


# ---- 원문 전문 수집 -----------------------------------------------------------
@check
def test_arxiv_abs_url_becomes_html_url():
    assert E.arxiv_html_url("https://arxiv.org/abs/2608.31100v1") == "https://arxiv.org/html/2608.31100v1"
    assert E.arxiv_html_url("http://www.arxiv.org/abs/1234.5678") == "http://arxiv.org/html/1234.5678"
    # arXiv 가 아니면 건드리지 않는다
    blog = "https://aws.amazon.com/blogs/machine-learning/foo/"
    assert E.arxiv_html_url(blog) == blog

@check
def test_extract_core_sections_keeps_only_key_parts():
    html = """<div class="ltx_abstract"><p>초록 본문이다.</p></div>
    <section id="S1"><h2>1 Introduction</h2><p>서론 내용 """ + "가"*150 + """</p></section>
    <section id="S2"><h2>2 Related Work</h2><p>버려야 할 관련연구 """ + "나"*150 + """</p></section>
    <section id="S9"><h2>7 Conclusion</h2><p>결론 내용 """ + "다"*150 + """</p></section>
    <script>var x=1;</script>"""
    out = E.extract_core_sections(html)
    assert "초록 본문" in out and "서론 내용" in out and "결론 내용" in out, out[:200]
    assert "관련연구" not in out, "본론 섹션까지 넣으면 토큰 한도를 넘는다"
    assert "var x" not in out, "script 가 남았다"

@check
def test_fulltext_failure_falls_back_without_raising():
    orig = E.fetch
    E.fetch = lambda url, timeout=None: (_ for _ in ()).throw(OSError("네트워크 끊김"))
    try:
        body, label = E.fetch_fulltext("https://arxiv.org/abs/1234.5678")
        assert body == "" and "OSError" in label, (body, label)
    finally:
        E.fetch = orig

@check
def test_fulltext_respects_token_ceiling():
    orig = E.fetch
    E.fetch = lambda url, timeout=None: (b"<article>" + "가".encode() * 60000 + b"</article>")
    try:
        body, _ = E.fetch_fulltext("https://aws.amazon.com/blogs/x/")
        assert len(body) == E.FULLTEXT_MAX, f"상한 미적용: {len(body)}"
    finally:
        E.fetch = orig


def main():
    failed = 0
    for fn in CHECKS:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
