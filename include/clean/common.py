"""Shared helpers for every cleaning module.

Pattern used everywhere:

    t = Tracker("orders")
    df = t.start(raw_df)                       # keeps a raw copy so rejects store the ORIGINAL row
    df = t.reject(df, bad_mask, "REASON_CODE") # rows leave `df` and go to the rejects table
    ...
    clean_df, rejects_df = t.finish(df)        # asserts rows_in == rows_out + rejected, logs counts

Do NOT reset_index inside a cleaning function after t.start(): the index is how a rejected
row is traced back to its raw copy.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

WINDOW_START = pd.Timestamp("2024-01-01")  # valid order dates (brief, section 4)
WINDOW_END = pd.Timestamp("2025-06-30")
UNKNOWN = "Unknown"
UNKNOWN_ID = "UNKNOWN"  # id used for the Unknown member of a dimension

REJECT_COLUMNS = ["source_file", "record_id", "reason_code", "detail", "raw_record"]

# Filled while the pipeline runs; run_all() resets and returns them.
STATS: list[dict] = []     # one row per entity/step: counts for the Data Quality Report
ID_MAPS: dict[str, pd.DataFrame] = {}   # "customer" / "product" -> (old_id, master_id)


# ------------------------------------------------------------------ small helpers
def norm_key(s: pd.Series) -> pd.Series:
    """strip + lowercase + collapse spaces; used to match label variants."""
    return s.str.strip().str.lower().str.replace(r"\s+", " ", regex=True)


def standardize(s: pd.Series, mapping: dict, default: str = UNKNOWN):
    """Map label variants to one canonical value. Returns (values, unmapped_mask).

    Missing source values and values not in `mapping` both become `default`;
    only the second kind is reported as unmapped (so new spellings are visible)."""
    key = norm_key(s)
    out = key.map(mapping)
    unmapped = (key.notna() & out.isna()).fillna(False).astype(bool)
    return out.fillna(default), unmapped


def to_number(s: pd.Series):
    """'Rs. 2,290' -> 2290.0. Returns (numbers, bad_mask) where bad = had a value but unparseable."""
    cleaned = s.str.replace(r"(?i)rs\.?|pkr|,", "", regex=True).str.strip()
    out = pd.to_numeric(cleaned, errors="coerce")
    bad = (s.notna() & out.isna()).fillna(False).astype(bool)
    return out, bad


SENTINEL = 9_999_999   # the source writes 9,999,999 as a placeholder in several numeric columns


def null_sentinel(s: pd.Series):
    """9,999,999 is a placeholder for 'unknown', not an amount. -> (values with NaN, mask of placeholders)."""
    hit = (s >= SENTINEL).fillna(False)
    return s.where(~hit), hit


QTY_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def parse_quantity(s: pd.Series):
    """'two' -> 2, '-3' -> 3, 'Rs'-style text stripped. Returns (quantity, was_word, was_negative)."""
    words = s.str.strip().str.lower().map(QTY_WORDS)
    is_word = words.notna()
    num, _ = to_number(s.where(~is_word))
    was_negative = (num < 0).fillna(False)
    qty = words.astype("float64").where(is_word, num.abs())
    return qty, is_word, was_negative


DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%b %d %Y")  # slash dates are day/month/year (brief)


def parse_dates(s: pd.Series):
    """Parse the 3 formats seen in the data. Impossible dates (2024-02-30, 00/00/2024) -> NaT.
    Returns (dates, bad_mask) where bad = had a value but could not be parsed."""
    s = s.str.strip()
    out = None
    for fmt in DATE_FORMATS:
        parsed = pd.to_datetime(s, format=fmt, errors="coerce")
        out = parsed if out is None else out.combine_first(parsed)
    bad = (s.notna() & out.isna()).fillna(False).astype(bool)
    return out, bad


def to_int(s: pd.Series) -> pd.Series:
    """'316.0' -> 316 (nullable Int64)."""
    return pd.to_numeric(s, errors="coerce").round().astype("Int64")


class UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def labels(self, index) -> pd.Series:
        return pd.Series({i: self.find(i) for i in index})


def link_by_keys(index, *key_series: pd.Series) -> pd.Series:
    """Group rows that share ANY non-null key value (transitively). Returns a group label per row."""
    uf = UnionFind(index)
    for keys in key_series:
        first = {}
        for idx, k in keys.dropna().items():
            if k in first:
                uf.union(first[k], idx)
            else:
                first[k] = idx
    return uf.labels(index)


def join_keys(*parts: pd.Series) -> pd.Series:
    """'a|b|c' per row, NaN when any part is missing (so missing values never match each other)."""
    return parts[0].str.cat(list(parts[1:]), sep="|")   # any NaN part -> NaN result


def make_rejects(raw_rows: pd.DataFrame, source_file: str, reason: str, detail: str = "") -> pd.DataFrame:
    if raw_rows.empty:
        return pd.DataFrame(columns=REJECT_COLUMNS)
    records = raw_rows.to_json(orient="records", lines=True, date_format="iso").splitlines()
    return pd.DataFrame({
        "source_file": source_file,
        "record_id": raw_rows.iloc[:, 0].astype(str).values,
        "reason_code": reason,
        "detail": detail,
        "raw_record": records,
    })[REJECT_COLUMNS]


def log_step(entity: str, rows_in: int, rows_out: int, rows_rejected: int = 0, **extra):
    row = {"entity": entity, "rows_in": rows_in, "rows_out": rows_out,
           "rows_rejected": rows_rejected, **extra}
    STATS.append(row)
    log.info("%s: %s", entity, row)


class Tracker:
    """Counts rows in / rejected / repaired for one file and enforces the reconciliation."""

    def __init__(self, entity: str):
        self.entity = entity
        self.source_file = f"{entity}.csv"
        self.rows_in = 0
        self._raw = None
        self._rejects: list[pd.DataFrame] = []
        self.rejected_by_reason: dict[str, int] = {}
        self.repairs: dict[str, int] = {}

    def start(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.reset_index(drop=True).copy()
        self.rows_in = len(df)
        self._raw = df.copy()          # raw strings, as read from the CSV
        return df

    def reject(self, df: pd.DataFrame, mask, reason: str, detail: str = "") -> pd.DataFrame:
        mask = pd.Series(mask, index=df.index).fillna(False).astype(bool)
        n = int(mask.sum())
        if n:
            self._rejects.append(make_rejects(self._raw.loc[df.index[mask]], self.source_file, reason, detail))
            self.rejected_by_reason[reason] = self.rejected_by_reason.get(reason, 0) + n
        return df[~mask]

    def drop_exact_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Exact duplicate rows (same value in every column): keep the first, reject the rest."""
        return self.reject(df, df.duplicated(keep="first"), "EXACT_DUPLICATE")

    def drop_duplicate_ids(self, df: pd.DataFrame, id_col: str) -> pd.DataFrame:
        """Same id but different content: keep the first. DECISION: document why 'first'."""
        return self.reject(df, df[id_col].duplicated(keep="first"), "DUPLICATE_ID", f"duplicate {id_col}")

    def repaired(self, rule: str, n) -> None:
        n = int(n)
        if n:
            self.repairs[rule] = self.repairs.get(rule, 0) + n

    def finish(self, df: pd.DataFrame):
        rejects = (pd.concat(self._rejects, ignore_index=True) if self._rejects
                   else pd.DataFrame(columns=REJECT_COLUMNS))
        assert self.rows_in == len(df) + len(rejects), (
            f"{self.entity}: rows_in={self.rows_in} != out={len(df)} + rejected={len(rejects)}")
        log_step(self.entity, self.rows_in, len(df), len(rejects),
                 rejected_by_reason=json.dumps(self.rejected_by_reason),
                 repairs=json.dumps(self.repairs))
        return df.reset_index(drop=True), rejects


def to_nullable_text(s: pd.Series) -> pd.Series:
    return s.replace({"": np.nan})
