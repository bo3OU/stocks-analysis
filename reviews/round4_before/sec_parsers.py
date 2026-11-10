"""Parsers for SEC ownership XML: Forms 3/4/5, Form 144, Schedule 13D/13G.

Each parser returns a list of flat dict rows (one per transaction / holding / reporting person) so they can be
written to CSV. Raw XML stays on disk; every row carries accession + source_url for traceability.
Parsing only extracts what the filing says; it does not interpret.
"""
from __future__ import annotations

from lxml import etree


def _t(el, path: str) -> str:
    r = el.xpath(path)
    if not r:
        return ""
    v = r[0]
    if isinstance(v, str):
        return v.strip()
    return (v.text or "").strip()


def _ln(el, name: str) -> list[str]:
    return [(e.text or "").strip() for e in el.xpath(f".//*[local-name()='{name}']") if (e.text or "").strip()]


def _first(el, name: str) -> str:
    v = _ln(el, name)
    return v[0] if v else ""


def parse_form345(path, accession: str, filed: str, source_url: str) -> list[dict]:
    tree = etree.parse(str(path))
    root = tree.getroot()
    doc_type = _t(root, "documentType")
    period = _t(root, "periodOfReport")
    issuer_cik = _t(root, "issuer/issuerCik")
    issuer_name = _t(root, "issuer/issuerName")
    issuer_sym = _t(root, "issuer/issuerTradingSymbol")
    flag_10b5 = _t(root, "aff10b5One")
    owners, titles, rels, owner_ciks = [], [], [], []
    for o in root.xpath("reportingOwner"):
        owners.append(_t(o, "reportingOwnerId/rptOwnerName"))
        owner_ciks.append(_t(o, "reportingOwnerId/rptOwnerCik"))
        flags = []
        for f, label in (("isDirector", "director"), ("isOfficer", "officer"),
                         ("isTenPercentOwner", "10%owner"), ("isOther", "other")):
            if _t(o, f"reportingOwnerRelationship/{f}").lower() in ("1", "true"):
                flags.append(label)
        rels.append("/".join(flags))
        titles.append(_t(o, "reportingOwnerRelationship/officerTitle"))
    owner_cik = _t(root, "reportingOwner/reportingOwnerId/rptOwnerCik")
    fn = {f.get("id"): (f.text or "").strip() for f in root.xpath("footnotes/footnote")}
    base = dict(accession=accession, filed=filed, form=doc_type, period_of_report=period, issuer_cik=issuer_cik,
                issuer=issuer_name, symbol=issuer_sym, owner="; ".join(owners), owner_cik=owner_cik,
                owner_ciks=";".join(c for c in owner_ciks if c),
                relationship="; ".join(r for r in rels if r), officer_title="; ".join(t for t in titles if t),
                rule_10b5_1=flag_10b5, source_url=source_url)

    def notes(el) -> str:
        ids = [x.get("id") for x in el.iter("footnoteId")]
        return " || ".join(fn.get(i, "") for i in dict.fromkeys(ids) if fn.get(i))

    rows: list[dict] = []
    for tx in root.xpath("nonDerivativeTable/nonDerivativeTransaction"):
        rows.append({**base, "table": "non_derivative_transaction",
                     "security": _t(tx, "securityTitle/value"), "date": _t(tx, "transactionDate/value"),
                     "code": _t(tx, "transactionCoding/transactionCode"),
                     "shares": _t(tx, "transactionAmounts/transactionShares/value"),
                     "price": _t(tx, "transactionAmounts/transactionPricePerShare/value"),
                     "acq_disp": _t(tx, "transactionAmounts/transactionAcquiredDisposedCode/value"),
                     "shares_after": _t(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"),
                     "direct_indirect": _t(tx, "ownershipNature/directOrIndirectOwnership/value"),
                     "nature": _t(tx, "ownershipNature/natureOfOwnership/value"), "footnotes": notes(tx)})
    for h in root.xpath("nonDerivativeTable/nonDerivativeHolding"):
        rows.append({**base, "table": "non_derivative_holding",
                     "security": _t(h, "securityTitle/value"), "date": period,
                     "shares_after": _t(h, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"),
                     "direct_indirect": _t(h, "ownershipNature/directOrIndirectOwnership/value"),
                     "nature": _t(h, "ownershipNature/natureOfOwnership/value"), "footnotes": notes(h)})
    for tx in root.xpath("derivativeTable/derivativeTransaction"):
        rows.append({**base, "table": "derivative_transaction",
                     "security": _t(tx, "securityTitle/value"), "date": _t(tx, "transactionDate/value"),
                     "code": _t(tx, "transactionCoding/transactionCode"),
                     "shares": _t(tx, "transactionAmounts/transactionShares/value"),
                     "price": _t(tx, "transactionAmounts/transactionPricePerShare/value"),
                     "acq_disp": _t(tx, "transactionAmounts/transactionAcquiredDisposedCode/value"),
                     "exercise_price": _t(tx, "conversionOrExercisePrice/value"),
                     "exercisable": _t(tx, "exerciseDate/value"), "expires": _t(tx, "expirationDate/value"),
                     "underlying": _t(tx, "underlyingSecurity/underlyingSecurityTitle/value"),
                     "underlying_shares": _t(tx, "underlyingSecurity/underlyingSecurityShares/value"),
                     "shares_after": _t(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"),
                     "direct_indirect": _t(tx, "ownershipNature/directOrIndirectOwnership/value"),
                     "nature": _t(tx, "ownershipNature/natureOfOwnership/value"), "footnotes": notes(tx)})
    for h in root.xpath("derivativeTable/derivativeHolding"):
        rows.append({**base, "table": "derivative_holding",
                     "security": _t(h, "securityTitle/value"), "date": period,
                     "exercise_price": _t(h, "conversionOrExercisePrice/value"),
                     "exercisable": _t(h, "exerciseDate/value"), "expires": _t(h, "expirationDate/value"),
                     "underlying": _t(h, "underlyingSecurity/underlyingSecurityTitle/value"),
                     "underlying_shares": _t(h, "underlyingSecurity/underlyingSecurityShares/value"),
                     "shares_after": _t(h, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"),
                     "footnotes": notes(h)})
    if not rows:  # still record that the filing exists (e.g. nothing parseable)
        rows.append({**base, "table": "none"})
    return rows


def parse_form144(path, accession: str, filed: str, source_url: str) -> list[dict]:
    root = etree.parse(str(path)).getroot()
    past = []
    for d, a, g in zip(_ln(root, "saleDate"), _ln(root, "amountOfSecuritiesSold"), _ln(root, "grossProceeds")):
        past.append(f"{d}:{a}:{g}")
    return [dict(accession=accession, filed=filed, form="144", issuer=_first(root, "issuerName"),
                 issuer_cik=_first(root, "issuerCik"),
                 person=_first(root, "nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold"),
                 relationship=_first(root, "relationshipToIssuer"), class_title=_first(root, "securitiesClassTitle"),
                 units_to_sell=_first(root, "noOfUnitsSold"), aggregate_market_value=_first(root, "aggregateMarketValue"),
                 units_outstanding=_first(root, "noOfUnitsOutstanding"), approx_sale_date=_first(root, "approxSaleDate"),
                 exchange=_first(root, "securitiesExchangeName"), acquired_date=_first(root, "acquiredDate"),
                 acquisition_nature=_first(root, "natureOfAcquisitionTransaction"),
                 plan_adoption_date=_first(root, "planAdoptionDate"), notice_date=_first(root, "noticeDate"),
                 remarks=_first(root, "remarks"), past_3m_sales=" | ".join(past), source_url=source_url)]


def parse_13dg(path, accession: str, filed: str, source_url: str) -> list[dict]:
    root = etree.parse(str(path)).getroot()
    base = dict(accession=accession, filed=filed, form=_first(root, "submissionType"), amendment_no=_first(root, "amendmentNo"),
                issuer=_first(root, "issuerName"), issuer_cik=_first(root, "issuerCik"), issuer_cusip=_first(root, "issuerCusipNumber"),
                class_title=_first(root, "securitiesClassTitle"),
                event_date=_first(root, "eventDateRequiresFilingThisStatement") or _first(root, "dateOfEvent"),
                filer=_first(root, "filingPersonName"), source_url=source_url)
    rows = []
    for c in root.xpath("//*[*[local-name()='reportingPersonName']]"):
        rows.append({**base, "reporting_person": _first(c, "reportingPersonName"),
                     "citizenship": _first(c, "citizenshipOrOrganization"),
                     "sole_voting": _first(c, "soleVotingPower"), "shared_voting": _first(c, "sharedVotingPower"),
                     "sole_dispositive": _first(c, "soleDispositivePower"),
                     "shared_dispositive": _first(c, "sharedDispositivePower"),
                     "aggregate_shares": _first(c, "reportingPersonBeneficiallyOwnedAggregateNumberOfShares"),
                     "percent_of_class": _first(c, "classPercent"), "person_type": _first(c, "typeOfReportingPerson")})
    if not rows:
        rows.append({**base, "reporting_person": _first(root, "reportingPersonName"),
                     "percent_of_class": _first(root, "classPercent"),
                     "aggregate_shares": _first(root, "amountBeneficiallyOwned")})
    return rows
