import { describe, expect, it } from 'vitest';
import { TokenError } from './api';
import { describeError } from './errors';

describe('describeError', () => {
  it('maps server error codes to caller-facing Arabic', () => {
    expect(describeError(new TokenError('rate_limited', 429)).title).toBe('محاولات كثيرة');
    expect(describeError(new TokenError('origin_forbidden', 403)).retryable).toBe(false);
  });
  it('detects a blocked microphone', () => {
    const err = new DOMException('denied', 'NotAllowedError');
    expect(describeError(err).title).toBe('الميكروفون محظور');
  });
  it('never exposes raw messages', () => {
    expect(describeError(new Error('secret stack')).detail).not.toContain('secret');
  });
});
