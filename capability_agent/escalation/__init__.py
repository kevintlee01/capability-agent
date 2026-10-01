"""Human-in-the-loop escalation: pause automation, hand the SAME live session
to a human, record what they do, then resume -- no fresh session, no co-browsing
infra. The seam is a tiny control-state file plus Playwright event listeners
that keep observing even while a human is driving.
"""
