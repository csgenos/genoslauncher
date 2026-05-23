"""Lightweight crash-log analyzer with actionable suggestions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrashSuggestion:
    title: str
    detail: str
    severity: str  # high, medium, low


def analyze_crash_text(text: str) -> list[CrashSuggestion]:
    blob = (text or "").lower()
    out: list[CrashSuggestion] = []

    def add(title: str, detail: str, severity: str = "medium") -> None:
        out.append(CrashSuggestion(title=title, detail=detail, severity=severity))

    if "outofmemoryerror" in blob or "java heap space" in blob:
        add(
            "Memory Exhausted",
            "Minecraft ran out of Java heap memory. Increase RAM for this instance or reduce heavy mods/shaders.",
            "high",
        )
    if "invalid maximum heap size" in blob or "could not reserve enough space" in blob:
        add(
            "Invalid JVM Memory Flags",
            "Current JVM memory settings are too high or invalid for this system. Lower RAM override and retry.",
            "high",
        )
    if "mixin" in blob and "failed" in blob:
        add(
            "Mod Mixin Conflict",
            "A mod mixin failed to apply. Update the affected modpack/mod versions and ensure loader compatibility.",
            "high",
        )
    if "modresolutionexception" in blob or "missing mandatory dependencies" in blob:
        add(
            "Missing Mod Dependencies",
            "One or more required dependencies are missing or wrong version. Reinstall/repair the instance.",
            "high",
        )
    if "nosuchmethoderror" in blob or "noclassdeffounderror" in blob:
        add(
            "Binary Incompatibility",
            "A mod likely targets a different game/loader/API version. Check recent mod updates and roll back if needed.",
            "high",
        )
    if "java.lang.unsatisfiedlinkerror" in blob or "opengl" in blob and "error" in blob:
        add(
            "Graphics/Driver Issue",
            "Graphics stack failed to initialize. Update GPU drivers, disable problematic shader packs, and retry.",
            "medium",
        )
    if "fabric-loader" in blob and "requires minecraft" in blob:
        add(
            "Loader/Game Version Mismatch",
            "Fabric loader and Minecraft target versions do not match. Reinstall loader for this exact MC version.",
            "medium",
        )
    if "authentication servers are down" in blob or "invalid session" in blob:
        add(
            "Authentication Session Problem",
            "Session/token appears invalid. Sign out and back in, then launch again.",
            "medium",
        )
    if "permission denied" in blob or "accessdeniedexception" in blob:
        add(
            "File Permission Denied",
            "Launcher or Java could not access required files. Check antivirus/file locks and folder permissions.",
            "medium",
        )
    if not out:
        add(
            "No Known Signature Matched",
            "No common crash signature detected. Use Repair, verify Java version, and review the first stacktrace cause.",
            "low",
        )
    return out[:8]

