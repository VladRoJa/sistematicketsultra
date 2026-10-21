/**
 * Coordinates a single refresh in this tab and delegates cross-tab exclusion
 * to the caller (navigator.locks). No credentials are logged or persisted here.
 */
export class RefreshCoordinator {
  private pending: Promise<string | null> | null = null;

  constructor(
    private readonly readToken: () => string | null,
    private readonly isUsable: (token: string) => boolean,
    private readonly exchange: (previousToken: string) => Promise<string | null>,
    private readonly runExclusively: (
      work: () => Promise<string | null>
    ) => Promise<string | null>,
  ) {}

  renew(observedToken: string | null): Promise<string | null> {
    if (!observedToken) {
      return Promise.resolve(null);
    }

    if (this.pending) {
      return this.pending;
    }

    const work = this.runExclusively(async () => {
      // Re-check after acquiring the cross-tab lock. Another tab may have
      // already rotated the shared HttpOnly cookie and saved a fresh JWT.
      const currentToken = this.readToken();
      if (!currentToken) {
        return null;
      }
      if (currentToken !== observedToken) {
        return this.isUsable(currentToken) ? currentToken : null;
      }
      return this.exchange(currentToken);
    });

    const pending = work.finally(() => {
      if (this.pending === pending) {
        this.pending = null;
      }
    });
    this.pending = pending;
    return pending;
  }
}
