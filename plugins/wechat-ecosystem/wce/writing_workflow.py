"""Offline writing-method versions and immutable, scoped refinements."""
import json
import os
from pathlib import Path
import re

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked, read_optional
from .service import digest

RULE_LIMIT = 16_384
REVIEW_LIMIT = 1_048_576
VERSION = re.compile(r'(?:0|[1-9][0-9]{0,3})(?:\.(?:0|[1-9][0-9]{0,3})){2}')
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,95}')
METHODS = {
    'lead_with_subject': '先交代主语、动作或变化，让开头本身提供信息。',
    'remove_empty_framing': '删掉不提供新信息的铺垫、重复结论及硬凑的升华。',
    'retain_evidence': '有出处的事实、引语、数字和范围逐项对照当前素材。',
    'follow_author_sample': '只借作者样稿的用词、节奏和语气，经历与数据来自当前素材。',
    'end_on_detail': '用具体观察、后果或下一步自然收尾。',
    'trim_repetition': '前后重复同一意思时优先保留更具体的一句。',
}
BASE = {
    'id': 'jiusera-writing', 'schema': 1, 'version': '1.0.0',
    'methods': ['lead_with_subject', 'remove_empty_framing', 'retain_evidence',
                'follow_author_sample', 'end_on_detail'],
    'genre_notes': {},
}
QUOTE = re.compile(r'「[^」]*」|『[^』]*』|“[^”]*”|"[^"\r\n]*"|^>[^\r\n]*', re.MULTILINE)
NUMBER = re.compile(r'(?<![0-9])[-+−]?\d+(?:[.,:/–-]\d+)*(?:\s*(?:%|％))?')
UNIT = re.compile(r'[-+−]?\d+(?:\.\d+)?[ \t]*(?:ppm|GHz|MHz|kHz|kg|mg|µg|μg|mm|cm|km|ms|mL|mW|kW|MW|Pa|kPa|MPa|°C|°F|℃|℉|s\b|m\b|g\b|L\b|h\b|W\b|V\b|分钟|小时|毫秒|毫米|厘米|千米|公里|千克|毫克|摄氏度|秒|米|克|元)')
CITATION = re.compile(r'\[(?:\d+(?:\s*[,，–-]\s*\d+)*)\]')


def require(condition, code='WRITING_INVALID_REQUEST'):
    if not condition:
        raise WCEError(code)


def pin(payload):
    return {'version': payload['version'], 'manifest_sha256': digest(payload)}


def envelope(payload):
    return {'rule': payload, 'manifest_sha256': digest(payload)}


def validate_package(data):
    require(isinstance(data, dict) and set(data) == {'rule', 'manifest_sha256'}, 'WRITING_RULE_INVALID')
    rule = data['rule']
    require(isinstance(rule, dict) and set(rule) == set(BASE), 'WRITING_RULE_INVALID')
    require(type(rule['schema']) is int and rule['schema'] == 1 and rule['id'] == BASE['id'],
            'WRITING_RULE_INCOMPATIBLE')
    methods = rule['methods']
    require(isinstance(rule['version'], str) and VERSION.fullmatch(rule['version'])
            and isinstance(methods, list) and 0 < len(methods) <= len(METHODS)
            and all(isinstance(method, str) and method in METHODS for method in methods)
            and len(methods) == len(set(methods))
            and 'retain_evidence' in methods,
            'WRITING_RULE_INVALID')
    notes = rule['genre_notes']
    require(isinstance(notes, dict) and set(notes) <= {'article', 'paper', 'copy'}
            and all(isinstance(note, str) and 0 < len(note.strip()) <= 240
                    and not any(ord(char) < 32 for char in note) for note in notes.values()),
            'WRITING_RULE_INVALID')
    require(data['manifest_sha256'] == digest(rule), 'WRITING_RULE_DIGEST_MISMATCH')
    return rule


def parse_package(text):
    require(len(text.encode()) <= RULE_LIMIT, 'WRITING_RULE_INVALID')

    def unique(pairs):
        result = dict(pairs)
        require(len(result) == len(pairs), 'WRITING_RULE_INVALID')
        return result

    try:
        package = json.loads(text, object_pairs_hook=unique)
    except (ValueError, RecursionError):
        raise WCEError('WRITING_RULE_INVALID') from None
    return validate_package(package)


def verify_text(original, revised, protected, genre):
    require(original.strip() and revised.strip())
    unchanged = (QUOTE.findall(original) == QUOTE.findall(revised)
                 and NUMBER.findall(original) == NUMBER.findall(revised)
                 and all(value.strip() and value in original and original.count(value) == revised.count(value)
                         for value in protected))
    if genre == 'paper':
        unchanged = (unchanged and UNIT.findall(original) == UNIT.findall(revised)
                     and CITATION.findall(original) == CITATION.findall(revised))
    require(unchanged, 'WRITING_PROTECTED_TEXT_CHANGED')


class WritingStore:
    def __init__(self, registry):
        self.root = Path(registry).parent / 'writing'

    def _read(self, filename, maximum=RULE_LIMIT):
        if not os.path.lexists(self.root):
            return None
        path_check(self.root, True)
        return read_optional(self.root / filename, maximum)

    def _ensure(self):
        for folder in (self.root.parent, self.root):
            folder.mkdir(mode=0o700, exist_ok=True)
            path_check(folder, True)

    def active(self):
        selected = self._read('active.json')
        if selected is None:
            return BASE
        return self.rules(selected)

    def rules(self, reference):
        require(isinstance(reference, dict) and set(reference) == {'version', 'manifest_sha256'}
                and isinstance(reference.get('version'), str) and VERSION.fullmatch(reference['version']),
                'WRITING_RULE_INVALID')
        version = reference['version']
        if version == BASE['version']:
            rule = BASE
        else:
            saved = self._read('rules-' + version + '.json')
            require(saved is not None, 'WRITING_RULE_NOT_FOUND')
            rule = validate_package(saved)
        require(reference == pin(rule), 'WRITING_RULE_DIGEST_MISMATCH')
        return rule

    def state(self):
        active = pin(self.active())
        rows = [pin(BASE)]
        if os.path.lexists(self.root):
            path_check(self.root, True)
            for file in self.root.glob('rules-*.json'):
                version = file.name[6:-5]
                if VERSION.fullmatch(version) and version != BASE['version']:
                    try:
                        rule = validate_package(self._read(file.name))
                        if rule['version'] == version:
                            rows.append(pin(rule))
                    except (WCEError, OSError):
                        continue
        rows.sort(key=lambda candidate: tuple(map(int, candidate['version'].split('.'))), reverse=True)
        return {'state': 'WRITING_RULES_READY', 'active': active, 'versions': rows}

    def change(self, expected, *, reference=None, package_text=None):
        candidate = parse_package(package_text) if package_text is not None else None
        reference = pin(candidate) if candidate is not None else reference
        self._ensure()
        with locked(self.root / 'write.lock'):
            selected = pin(self.active())
            require(selected == expected or selected == reference, 'WRITING_RULE_SELECTION_CHANGED')
            if candidate is not None:
                version = candidate['version']
                if version == BASE['version']:
                    require(candidate == BASE, 'WRITING_RULE_VERSION_CONFLICT')
                else:
                    filename = 'rules-' + version + '.json'
                    previous = self._read(filename)
                    require(previous is None or previous == envelope(candidate), 'WRITING_RULE_VERSION_CONFLICT')
                    if previous is None:
                        atomic_write(self.root / filename, envelope(candidate), RULE_LIMIT)
            self.rules(reference)
            if selected != reference:
                atomic_write(self.root / 'active.json', reference)
            return self.state()

    def read_draft(self, owner, draft_id):
        require(IDENTIFIER.fullmatch(draft_id))
        key = digest([owner, draft_id])
        record = self._read('draft-' + key + '.json', REVIEW_LIMIT)
        if record is not None:
            require(isinstance(record, dict) and record.get('owner') == owner and record.get('draft_id') == draft_id
                    and isinstance(record.get('record'), dict)
                    and digest(record['record']) == record.get('record_sha256'), 'WRITING_DRAFT_CHANGED')
        return record

    def save_draft(self, owner, draft_id, request_sha, record):
        require(IDENTIFIER.fullmatch(draft_id))
        self._ensure()
        with locked(self.root / 'write.lock'):
            previous = self.read_draft(owner, draft_id)
            if previous is not None:
                require(previous['request_sha256'] == request_sha, 'WRITING_DRAFT_CONFLICT')
                return previous
            value = {'owner': owner, 'draft_id': draft_id, 'request_sha256': request_sha,
                     'record': record, 'record_sha256': digest(record)}
            key = digest([owner, draft_id])
            atomic_write(self.root / ('draft-' + key + '.json'), value, REVIEW_LIMIT)
            return value
