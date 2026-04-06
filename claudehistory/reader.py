import json
import re
from pathlib import Path


def _is_session_file(stem: str) -> bool:
    return bool(re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', stem))

def _read_cwd(path: Path) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                cwd = obj.get("cwd")
                if cwd:
                    return cwd
    except Exception:
        pass
    return None

def _read_session_meta(path: Path) -> tuple:
    title = path.stem
    timestamp = None
    msg_count = 0
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                t = obj.get("type")
                if t == "ai-title":
                    title = obj.get("aiTitle", title)
                elif t in ("user", "assistant"):
                    msg_count += 1
                    if timestamp is None:
                        timestamp = obj.get("timestamp")
    except Exception:
        pass
    return title, timestamp, msg_count

def _process_message(obj: dict) -> dict | None:
    role = obj.get("type")
    raw_content = obj.get("message", {}).get("content", [])

    # Normalize to list
    if isinstance(raw_content, str):
        raw_content = [{"type": "text", "text": raw_content}]
    elif not isinstance(raw_content, list):
        return None

    text_parts = []
    thinking_blocks = []
    tool_uses = []
    images = []
    has_user_text = False

    for block in raw_content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            t = block.get("text", "")
            # Filter out ide_opened_file system injections
            t = re.sub(r'<ide_opened_file>.*?</ide_opened_file>', '', t, flags=re.DOTALL).strip()
            t = re.sub(r'<ide_selection>.*?</ide_selection>', '', t, flags=re.DOTALL).strip()
            if t:
                text_parts.append(t)
                has_user_text = True
        elif btype == "thinking":
            t = block.get("thinking", "")
            if t:
                thinking_blocks.append(t)
        elif btype == "tool_use":
            tool_uses.append(_process_tool_use(block))
        elif btype == "tool_result":
            inner = block.get("content", "")
            if isinstance(inner, str) and block.get("is_error"):
                # Extract user-supplied reason from tool rejection messages
                marker = "The user provided the following reason for the rejection:"
                idx = inner.find(marker)
                if idx != -1:
                    reason = inner[idx + len(marker):].strip()
                    if reason:
                        text_parts.append(reason)
                        has_user_text = True
            elif isinstance(inner, list):
                for item in inner:
                    if isinstance(item, dict) and item.get("type") == "image":
                        src = item.get("source", {})
                        images.append({
                            "media_type": src.get("media_type", "image/png"),
                            "data": src.get("data", ""),
                        })

    # Skip user messages that are only tool results (no real text)
    if role == "user" and not has_user_text:
        return None

    # Skip assistant messages with no displayable content
    if role == "assistant" and not text_parts and not tool_uses and not thinking_blocks:
        return None

    # Detect plan-mode injection ("Implement the following plan:")
    plan_content = obj.get("planContent")

    return {
        "uuid": obj.get("uuid", ""),
        "role": role,
        "timestamp": obj.get("timestamp", ""),
        "text": "\n\n".join(text_parts),
        "thinking": thinking_blocks,
        "tool_uses": tool_uses,
        "images": images,
        "plan_content": plan_content,
    }

def _process_tool_use(block: dict) -> dict:
    name = block.get("name", "unknown")
    inp = block.get("input", {})
    file_path = None
    description = ""

    if name in ("Read", "Write", "Edit", "NotebookEdit", "NotebookRead"):
        file_path = inp.get("file_path") or inp.get("notebook_path", "")
        description = file_path or ""
    elif name == "Glob":
        description = inp.get("pattern", "")
        if inp.get("path"):
            description += f" in {inp['path']}"
    elif name == "Grep":
        description = inp.get("pattern", "")
        if inp.get("path"):
            description += f" in {inp['path']}"
    elif name == "Bash":
        cmd = inp.get("command", "")
        description = cmd[:100]
    elif name in ("WebFetch", "WebSearch"):
        description = (inp.get("url") or inp.get("query") or "")[:80]
    elif name == "Agent":
        description = inp.get("description") or inp.get("prompt", "")[:60]
    else:
        for v in inp.values():
            if isinstance(v, str) and v:
                description = v[:80]
                break

    return {"name": name, "file": file_path, "description": description}

def _search_message(obj: dict, query: str, search_type: str) -> dict | None:
    role = obj.get("type", "")
    uuid = obj.get("uuid", "")
    timestamp = obj.get("timestamp", "")
    content = obj.get("message", {}).get("content", [])
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]

    if search_type == "file":
        for block in (content if isinstance(content, list) else []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                inp = block.get("input", {})
                fp = inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
                if query in fp.lower():
                    return {"role": role, "uuid": uuid, "timestamp": timestamp,
                            "snippet": f"📄 {fp}", "match_type": "file"}
    else:
        full_text = ""
        for block in (content if isinstance(content, list) else []):
            if isinstance(block, dict) and block.get("type") == "text":
                full_text += block.get("text", "") + " "
        if isinstance(content, str):
            full_text = content
        if query in full_text.lower():
            idx = full_text.lower().find(query)
            s = max(0, idx - 60)
            e = min(len(full_text), idx + len(query) + 120)
            snippet = ("…" if s > 0 else "") + full_text[s:e] + ("…" if e < len(full_text) else "")
            return {"role": role, "uuid": uuid, "timestamp": timestamp,
                    "snippet": snippet, "match_type": "text"}
    return None


class ClaudeDataReader:
    def __init__(self, claude_dir: Path):
        self.claude_dir = claude_dir
        self.projects_dir = claude_dir / "projects"

    # ---- Projects ----

    def list_projects(self) -> list:
        if not self.projects_dir.exists():
            return []
        projects = []
        for proj_dir in self.projects_dir.iterdir():
            if not proj_dir.is_dir():
                continue
            cwd, first_ts, last_ts, session_count = self._project_summary(proj_dir)
            if session_count == 0:
                continue
            projects.append({
                "id": proj_dir.name,
                "cwd": cwd or proj_dir.name,
                "session_count": session_count,
                "first_activity": first_ts,
                "last_activity": last_ts,
            })
        projects.sort(key=lambda x: x["last_activity"] or "", reverse=True)
        return projects

    def _project_summary(self, proj_dir: Path):
        cwd = None
        first_ts = None
        last_ts = None
        session_count = 0
        for f in proj_dir.glob("*.jsonl"):
            if not _is_session_file(f.stem):
                continue
            session_count += 1
            _, ts, _ = _read_session_meta(f)
            if ts:
                if first_ts is None or ts < first_ts:
                    first_ts = ts
                if last_ts is None or ts > last_ts:
                    last_ts = ts
            if cwd is None:
                cwd = _read_cwd(f)
        return cwd, first_ts, last_ts, session_count

    # ---- Sessions ----

    def list_sessions(self, project_id: str) -> list:
        proj_dir = self.projects_dir / project_id
        if not proj_dir.is_dir():
            return []
        sessions = []
        for f in proj_dir.glob("*.jsonl"):
            if not _is_session_file(f.stem):
                continue
            title, timestamp, msg_count = _read_session_meta(f)
            sessions.append({
                "id": f.stem,
                "title": title,
                "timestamp": timestamp,
                "message_count": msg_count,
            })
        sessions.sort(key=lambda x: x["timestamp"] or "", reverse=True)
        return sessions

    # ---- Messages ----

    def get_messages(self, project_id: str, session_id: str) -> list:
        f = self.projects_dir / project_id / f"{session_id}.jsonl"
        if not f.exists():
            return []
        messages = []
        skill_expansion_pending = False
        with open(f, encoding="utf-8", errors="replace") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("type") not in ("user", "assistant"):
                        continue
                    # Skip lines that belong to a different session (cross-session contamination)
                    if obj.get("sessionId") and obj.get("sessionId") != session_id:
                        continue
                    # Track Skill tool_use in assistant messages; the following user text
                    # message is the skill expansion injected by the harness, not real user input.
                    if obj.get("type") == "assistant":
                        content = obj.get("message", {}).get("content", [])
                        skill_expansion_pending = isinstance(content, list) and any(
                            isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Skill"
                            for b in content
                        )
                    msg = _process_message(obj)
                    if msg:
                        if msg["role"] == "user" and skill_expansion_pending:
                            # This is the skill-expanded prompt injected as a user message; skip it.
                            skill_expansion_pending = False
                            continue
                        messages.append(msg)
                except Exception:
                    pass
        return messages

    # ---- Search ----

    def search(self, query: str, project_id: str = None, search_type: str = "text", max_results: int = 300) -> list:
        q = query.lower()
        results = []

        if project_id:
            dirs = [(project_id, self.projects_dir / project_id)]
        else:
            dirs = [(d.name, d) for d in self.projects_dir.iterdir() if d.is_dir()]

        for proj_id, proj_dir in dirs:
            for f in proj_dir.glob("*.jsonl"):
                if not _is_session_file(f.stem):
                    continue
                session_id = f.stem
                title = session_id
                hits = []
                with open(f, encoding="utf-8", errors="replace") as fp:
                    for line in fp:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            if obj.get("type") == "ai-title":
                                title = obj.get("aiTitle", title)
                            elif obj.get("type") in ("user", "assistant"):
                                hit = _search_message(obj, q, search_type)
                                if hit:
                                    hit.update({"project_id": proj_id, "session_id": session_id})
                                    hits.append(hit)
                        except Exception:
                            pass
                for h in hits:
                    h["session_title"] = title
                    results.append(h)
                if len(results) >= max_results:
                    return results
        return results
