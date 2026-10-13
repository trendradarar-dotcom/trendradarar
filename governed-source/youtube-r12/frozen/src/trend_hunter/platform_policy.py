from __future__ import annotations

from copy import deepcopy
from typing import Any

PLATFORM_POLICY_CATALOG_VERSION = "2026-09-13"

PLATFORM_POLICY_SOURCES: dict[str, tuple[str, ...]] = {
    "youtube": ("https://support.google.com/youtube/answer/9288567",),
    "tiktok": ("https://www.tiktok.com/community-guidelines",),
    "instagram": ("https://help.instagram.com/477434105621119",),
    "snapchat": ("https://values.snap.com/policy/policy-community-guidelines",),
}


def _rule(rule_id: str, title: str, review_prompt: str, source_url: str) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "title": title,
        "review_prompt": review_prompt,
        "source_url": source_url,
        "source_kind": "OFFICIAL_PLATFORM_POLICY",
        "catalog_version": PLATFORM_POLICY_CATALOG_VERSION,
    }


PLATFORM_POLICY_RULES: dict[str, tuple[dict[str, Any], ...]] = {
    "youtube": (
        _rule("YT-SPAM-DECEPTION", "Spam, deceptive practices, scams and fake engagement",
              "Review the material for spam, scams, impersonation, deceptive links, manipulated engagement, or other deceptive practices.",
              PLATFORM_POLICY_SOURCES["youtube"][0]),
        _rule("YT-SENSITIVE", "Sensitive content, minors, sexual content and self-harm",
              "Review nudity/sexual content, child-safety issues, self-harm/eating-disorder content, vulgar or age-sensitive material, and contextual exceptions.",
              PLATFORM_POLICY_SOURCES["youtube"][0]),
        _rule("YT-VIOLENCE-DANGER", "Violent, hateful, dangerous and harassing content",
              "Review threats, graphic violence, dangerous acts, hate speech, harassment/cyberbullying, and violent criminal organizations.",
              PLATFORM_POLICY_SOURCES["youtube"][0]),
        _rule("YT-REGULATED-GOODS", "Illegal or regulated goods and services",
              "Review sale, promotion, facilitation, or links involving prohibited or regulated goods/services, including firearms and other restricted items.",
              PLATFORM_POLICY_SOURCES["youtube"][0]),
        _rule("YT-MISINFORMATION", "Harmful misinformation",
              "Review misleading or deceptive claims that may create serious real-world harm, including manipulated content and covered medical/civic misinformation.",
              PLATFORM_POLICY_SOURCES["youtube"][0]),
        _rule("YT-RIGHTS-AUTHENTICITY", "Rights, ownership and authentic presentation",
              "Confirm the publisher has the rights/authorization needed for the material and is not deceptively presenting another person, channel, brand, or source.",
              PLATFORM_POLICY_SOURCES["youtube"][0]),
    ),
    "tiktok": (
        _rule("TT-SAFETY-CIVILITY", "Safety, violence, criminal behavior, hate and harassment",
              "Review violence or threats, criminal promotion, hateful behavior, violent/hateful organizations, trafficking, harassment and bullying.",
              PLATFORM_POLICY_SOURCES["tiktok"][0]),
        _rule("TT-MENTAL-BEHAVIORAL", "Mental and behavioral health",
              "Review suicide/self-harm, disordered eating/body-image harm, dangerous activities, and challenge content.",
              PLATFORM_POLICY_SOURCES["tiktok"][0]),
        _rule("TT-SENSITIVE-MATURE", "Sensitive and mature themes",
              "Review sexual activity/services, nudity/body exposure, sexually suggestive content, shocking/graphic content, and animal abuse.",
              PLATFORM_POLICY_SOURCES["tiktok"][0]),
        _rule("TT-INTEGRITY-AUTHENTICITY", "Integrity, misinformation, AI/editing and fake engagement",
              "Review harmful misinformation, civic/election integrity, realistic edited/AI-generated content labeling, deceptive behavior, and fake engagement.",
              PLATFORM_POLICY_SOURCES["tiktok"][0]),
        _rule("TT-IP-ORIGINALITY", "Originality and intellectual-property rights",
              "Confirm the material is original or properly authorized and does not infringe copyright, trademark, or other rights.",
              PLATFORM_POLICY_SOURCES["tiktok"][0]),
        _rule("TT-REGULATED-COMMERCIAL", "Regulated goods, commercial activity and disclosure",
              "Review regulated/high-risk goods or services, fraud/scams, and whether product/brand/business promotion requires TikTok commercial-content disclosure.",
              PLATFORM_POLICY_SOURCES["tiktok"][0]),
        _rule("TT-PRIVACY-SECURITY", "Privacy and security",
              "Review personal information, doxxing/privacy risks, account or platform-security abuse, malicious links, or security circumvention.",
              PLATFORM_POLICY_SOURCES["tiktok"][0]),
    ),
    "instagram": (
        _rule("IG-RIGHTS-ORIGINALITY", "Ownership and right to share",
              "Confirm the material was created by the publisher or the publisher has the right/permission to share it.",
              PLATFORM_POLICY_SOURCES["instagram"][0]),
        _rule("IG-NUDITY-SENSITIVE", "Nudity, sexual content and sensitive material",
              "Review nudity/sexual content, sexual exploitation, minors, intimate imagery, and context-sensitive exceptions.",
              PLATFORM_POLICY_SOURCES["instagram"][0]),
        _rule("IG-VIOLENCE-HATE", "Violence, threats, hate and dangerous organizations",
              "Review credible threats, encouragement/glorification of violence, hate, terrorism/organized crime support, and graphic violence.",
              PLATFORM_POLICY_SOURCES["instagram"][0]),
        _rule("IG-HARASSMENT-PRIVACY", "Harassment, bullying and private information",
              "Review degrading/shaming attacks, blackmail, doxxing/private information, repeated unwanted contact, and harassment.",
              PLATFORM_POLICY_SOURCES["instagram"][0]),
        _rule("IG-SELF-HARM", "Self-harm and eating-disorder promotion",
              "Review content that encourages or glorifies self-injury, suicide, eating disorders, or harmful behaviors.",
              PLATFORM_POLICY_SOURCES["instagram"][0]),
        _rule("IG-REGULATED-ILLEGAL", "Illegal and regulated goods/services",
              "Review regulated goods/services, drugs, firearms, alcohol/tobacco transactions, gambling permissions, endangered-species trade, and other unlawful activity.",
              PLATFORM_POLICY_SOURCES["instagram"][0]),
        _rule("IG-SPAM-DECEPTION", "Spam, fake engagement, impersonation and deception",
              "Review repetitive/spam behavior, artificial likes/followers/reviews, misleading identity/impersonation, fraud, or deceptive conduct.",
              PLATFORM_POLICY_SOURCES["instagram"][0]),
    ),
    "snapchat": (
        _rule("SC-SEXUAL", "Sexual content and exploitation",
              "Review sexual exploitation/abuse, minors, pornography, non-consensual intimate imagery, sextortion, sexual harassment, and sexual services.",
              PLATFORM_POLICY_SOURCES["snapchat"][0]),
        _rule("SC-VIOLENCE-HARM", "Threats, violence, dangerous behavior and self-harm",
              "Review threats, dangerous behavior, graphic violence/injury, animal abuse, and promotion or assistance of self-harm.",
              PLATFORM_POLICY_SOURCES["snapchat"][0]),
        _rule("SC-HATE-EXTREMISM", "Hateful content, terrorism and violent extremism",
              "Review hate speech/discrimination and support, glorification, praise, or advocacy for terrorist, violent extremist, or hate groups.",
              PLATFORM_POLICY_SOURCES["snapchat"][0]),
        _rule("SC-HARASSMENT-PRIVACY", "Harassment, bullying and privacy",
              "Review bullying, shaming, rumor-spreading, unwanted contact, manipulated humiliating imagery, doxxing, and non-consensual private information.",
              PLATFORM_POLICY_SOURCES["snapchat"][0]),
        _rule("SC-ILLEGAL-REGULATED", "Illegal or regulated activities",
              "Review illegal activity, trafficking/smuggling, organized crime, illicit or prescription drugs, weapons/explosives, and other regulated activity.",
              PLATFORM_POLICY_SOURCES["snapchat"][0]),
        _rule("SC-FALSE-DECEPTIVE", "Harmful false or deceptive practices",
              "Review harmful false information, unsubstantiated medical claims, civic-process deception, misleading AI/editing, impersonation, fraud, and spam.",
              PLATFORM_POLICY_SOURCES["snapchat"][0]),
        _rule("SC-ECOSYSTEM-INTEGRITY", "Platform and ecosystem integrity",
              "Review inauthentic activity or deceptive practices intended to manipulate Snapchat, its products, distribution, or user trust.",
              PLATFORM_POLICY_SOURCES["snapchat"][0]),
    ),
}


def normalize_platform(platform: str) -> str:
    p = str(platform or "").strip().lower()
    aliases = {
        "yt": "youtube", "youtube": "youtube",
        "tt": "tiktok", "tik_tok": "tiktok", "tiktok": "tiktok",
        "ig": "instagram", "instagram": "instagram",
        "snap": "snapchat", "snapchat": "snapchat",
    }
    if p not in aliases:
        raise ValueError(f"unsupported platform policy catalog: {platform!r}")
    return aliases[p]


def platform_policy_rules(platform: str) -> list[dict[str, Any]]:
    p = normalize_platform(platform)
    return [deepcopy(rule) for rule in PLATFORM_POLICY_RULES[p]]


def platform_findings_for_review(platform: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for rule in platform_policy_rules(platform):
        findings.append({
            **rule,
            "status": "UNRESOLVED",
            "reason": "Human platform-policy review is required for this exact creative.",
            "evidence_state_ids": [],
        })
    return findings


def supported_platforms() -> tuple[str, ...]:
    return tuple(sorted(PLATFORM_POLICY_RULES))