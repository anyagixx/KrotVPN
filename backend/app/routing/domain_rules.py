"""
Domain and CIDR routing rule persistence helpers.

MODULE_CONTRACT
- PURPOSE: Normalize, validate, and persist domain or CIDR policy rules for later route resolution.
- SCOPE: Domain normalization, CIDR normalization, duplicate detection, ordered reads, and CRUD-style store helpers.
- DEPENDS: M-001 database session lifecycle, M-014 rule entities in app.routing.models.
- LINKS: M-014 domain-rule-store, M-013 route-policy-resolver, V-M-014.

MODULE_MAP
- RuleValidationError: Raised for invalid or conflicting routing rules.
- normalize_domain_rule_input: Converts domain input into canonical normalized form and match type.
- normalize_cidr_rule_input: Converts IP/CIDR input into canonical network form.
- DomainRuleStore: Async persistence helper for domain and CIDR policy rules.

CHANGE_SUMMARY
- 2026-03-24: Added first-pass rule store for exact-domain, wildcard-domain, and CIDR policy persistence.
"""
# <!-- GRACE: module="M-014" contract="domain-rule-store" -->

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.routing.models import (
    CidrRouteRule,
    CidrRouteRuleCreate,
    CidrRouteRuleUpdate,
    DomainMatchType,
    DomainRouteRule,
    DomainRouteRuleCreate,
    DomainRouteRuleUpdate,
)


class RuleValidationError(ValueError):
    """Raised when a routing policy rule cannot be normalized or persisted safely."""


@dataclass(frozen=True)
class NormalizedDomainRule:
    raw_domain: str
    normalized_domain: str
    match_type: DomainMatchType


def normalize_domain_rule_input(domain: str) -> NormalizedDomainRule:
    """Normalize domain input and classify it as exact or wildcard."""
    raw = domain.strip()
    if not raw:
        raise RuleValidationError("Domain rule cannot be empty")

    lowered = raw.lower().rstrip(".")
    if not lowered:
        raise RuleValidationError("Domain rule cannot be empty")

    if lowered.startswith("*."):
        normalized = lowered[2:]
        match_type = DomainMatchType.WILDCARD
    else:
        normalized = lowered
        match_type = DomainMatchType.EXACT

    if not normalized or normalized.startswith("."):
        raise RuleValidationError("Domain rule is malformed")
    if "*" in normalized:
        raise RuleValidationError("Wildcard is only supported as a leading '*.' prefix")
    if ".." in normalized:
        raise RuleValidationError("Domain rule cannot contain empty labels")

    labels = normalized.split(".")
    if len(labels) < 2:
        raise RuleValidationError("Domain rule must include at least one dot-separated suffix")
    for label in labels:
        if not label or len(label) > 63:
            raise RuleValidationError("Domain label length is invalid")
        if label.startswith("-") or label.endswith("-"):
            raise RuleValidationError("Domain labels cannot start or end with '-'")
        if not all(ch.isalnum() or ch == "-" for ch in label):
            raise RuleValidationError("Domain rule contains unsupported characters")

    return NormalizedDomainRule(
        raw_domain=lowered,
        normalized_domain=normalized,
        match_type=match_type,
    )


def normalize_cidr_rule_input(cidr: str) -> str:
    """Normalize a single IP or CIDR string into a canonical network form."""
    raw = cidr.strip()
    if not raw:
        raise RuleValidationError("CIDR rule cannot be empty")

    try:
        network = ipaddress.ip_network(raw, strict=False)
    except ValueError as exc:
        raise RuleValidationError(f"Invalid IP or CIDR rule: {cidr}") from exc

    return str(network)


class DomainRuleStore:
    """Persistence helper for domain and CIDR routing rules."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_domain_rule(self, payload: DomainRouteRuleCreate) -> DomainRouteRule:
        """Create a normalized domain rule and reject duplicates."""
        normalized = normalize_domain_rule_input(payload.domain)
        existing = await self._find_domain_rule(
            normalized.normalized_domain,
            normalized.match_type,
        )
        if existing is not None:
            raise RuleValidationError("Domain rule already exists")

        rule = DomainRouteRule(
            domain=normalized.raw_domain,
            normalized_domain=normalized.normalized_domain,
            match_type=normalized.match_type,
            route_target=payload.route_target,
            priority=payload.priority,
            description=payload.description,
        )
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def update_domain_rule(
        self,
        rule: DomainRouteRule,
        payload: DomainRouteRuleUpdate,
    ) -> DomainRouteRule:
        """Apply an in-place update to a domain rule."""
        if payload.route_target is not None:
            rule.route_target = payload.route_target
        if payload.priority is not None:
            rule.priority = payload.priority
        if payload.description is not None:
            rule.description = payload.description
        if payload.is_active is not None:
            rule.is_active = payload.is_active
        rule.updated_at = datetime.utcnow()
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def create_cidr_rule(self, payload: CidrRouteRuleCreate) -> CidrRouteRule:
        """Create a normalized CIDR rule and reject duplicates."""
        normalized_cidr = normalize_cidr_rule_input(payload.cidr)
        existing = await self._find_cidr_rule(normalized_cidr)
        if existing is not None:
            raise RuleValidationError("CIDR rule already exists")

        rule = CidrRouteRule(
            cidr=payload.cidr.strip(),
            normalized_cidr=normalized_cidr,
            route_target=payload.route_target,
            priority=payload.priority,
            description=payload.description,
        )
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def update_cidr_rule(
        self,
        rule: CidrRouteRule,
        payload: CidrRouteRuleUpdate,
    ) -> CidrRouteRule:
        """Apply an in-place update to a CIDR rule."""
        if payload.route_target is not None:
            rule.route_target = payload.route_target
        if payload.priority is not None:
            rule.priority = payload.priority
        if payload.description is not None:
            rule.description = payload.description
        if payload.is_active is not None:
            rule.is_active = payload.is_active
        rule.updated_at = datetime.utcnow()
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def list_active_domain_rules(self) -> list[DomainRouteRule]:
        """Return active domain rules ordered by priority and specificity."""
        result = await self.session.execute(
            select(DomainRouteRule)
            .where(DomainRouteRule.is_active == True)
            .order_by(
                DomainRouteRule.priority.asc(),
                DomainRouteRule.match_type.asc(),
                DomainRouteRule.normalized_domain.asc(),
            )
        )
        return list(result.scalars().all())

    async def list_active_cidr_rules(self) -> list[CidrRouteRule]:
        """Return active CIDR rules ordered by priority."""
        result = await self.session.execute(
            select(CidrRouteRule)
            .where(CidrRouteRule.is_active == True)
            .order_by(
                CidrRouteRule.priority.asc(),
                CidrRouteRule.normalized_cidr.asc(),
            )
        )
        return list(result.scalars().all())

    async def _find_domain_rule(
        self,
        normalized_domain: str,
        match_type: DomainMatchType,
    ) -> DomainRouteRule | None:
        """Look up a domain rule by canonical key."""
        result = await self.session.execute(
            select(DomainRouteRule).where(
                DomainRouteRule.normalized_domain == normalized_domain,
                DomainRouteRule.match_type == match_type,
            )
        )
        return result.scalar_one_or_none()

    async def _find_cidr_rule(self, normalized_cidr: str) -> CidrRouteRule | None:
        """Look up a CIDR rule by canonical key."""
        result = await self.session.execute(
            select(CidrRouteRule).where(CidrRouteRule.normalized_cidr == normalized_cidr)
        )
        return result.scalar_one_or_none()
