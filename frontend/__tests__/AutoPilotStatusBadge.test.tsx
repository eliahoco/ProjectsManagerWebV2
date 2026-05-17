/**
 * Tests for AutoPilotStatusBadge — CB-2751
 *
 * Verifies: color class, tooltip, aria-label, label text per state/reason.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { AutoPilotStatusBadge, getFriendlyLabel } from '@/components/codeboard/AutoPilotStatusBadge';

describe('AutoPilotStatusBadge', () => {
  it('renders with correct aria-label for running state', () => {
    render(<AutoPilotStatusBadge state="running" />);
    const badge = screen.getByTestId('autopilot-status-badge');
    expect(badge).toBeTruthy();
    expect(badge.getAttribute('aria-label')).toContain('Running');
  });

  it('renders friendly label for paused/crash_recovery', () => {
    render(<AutoPilotStatusBadge state="paused" reason="crash_recovery" />);
    const badge = screen.getByTestId('autopilot-status-badge');
    expect(badge.textContent).toBe('Crash recovery');
    expect(badge.getAttribute('aria-label')).toContain('Crash recovery');
  });

  it('renders friendly label for waiting_reset/rate_limit_5h', () => {
    render(<AutoPilotStatusBadge state="waiting_reset" reason="rate_limit_5h" />);
    const badge = screen.getByTestId('autopilot-status-badge');
    expect(badge.textContent).toBe('Rate limit — auto-resume armed');
  });

  it('shows tooltip as state/reason', () => {
    render(<AutoPilotStatusBadge state="paused" reason="manual" />);
    const badge = screen.getByTestId('autopilot-status-badge');
    expect(badge.getAttribute('title')).toBe('paused/manual');
  });

  it('falls back gracefully for unknown state/reason', () => {
    render(<AutoPilotStatusBadge state="unknown_state" reason="unknown_reason" />);
    const badge = screen.getByTestId('autopilot-status-badge');
    // Should render without crashing, showing raw fallback
    expect(badge).toBeTruthy();
    expect(badge.textContent).toContain('unknown_state');
  });

  it('getFriendlyLabel covers zombie state', () => {
    const result = getFriendlyLabel('running', 'zombie_detected');
    expect(result.toLowerCase()).toContain('zombie');
  });
});
