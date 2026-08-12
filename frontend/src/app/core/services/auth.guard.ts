import { inject } from '@angular/core';
import { CanActivateFn, Router, UrlTree } from '@angular/router';

import { AuthService } from './auth.service';

/**
 * No view without a session.
 *
 * The guard **awaits** the restore rather than reading `authenticated()`
 * directly, and that is the whole reason it is written as an async function.
 * On a hard refresh the token is in storage but the user object is not yet
 * there: `restore()` has been dispatched and has not come back. A synchronous
 * check reads `null`, decides the researcher is a stranger, and redirects to
 * the login screen — for someone who is, in fact, logged in. The bug appears
 * only on reload, never during navigation, which is exactly the sort that
 * survives manual testing.
 *
 * `restore()` is memoised in the service, so guarding every route costs one
 * `/auth/me` per page load rather than one per navigation.
 *
 * The attempted URL is carried to the login screen as `redirect`, because
 * landing on the laboratory after signing in — when you clicked a link to the
 * movement log — is a small, repeated insult.
 */
async function requireSession(attemptedUrl: string): Promise<true | UrlTree> {
  const auth = inject(AuthService);
  const router = inject(Router);

  await auth.restore();

  if (auth.authenticated()) return true;

  return router.createUrlTree(['/login'], {
    queryParams: attemptedUrl && attemptedUrl !== '/login' ? { redirect: attemptedUrl } : {},
  });
}

export const authGuard: CanActivateFn = (_route, state) => requireSession(state.url);

/**
 * The mirror image: keep a signed-in user off the login screen.
 *
 * Without it, `/login` stays reachable while authenticated, and a user who
 * bookmarked it gets a form that will simply issue a second token for the
 * session they already have.
 */
export const guestGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  await auth.restore();

  return auth.authenticated() ? router.createUrlTree(['/lab']) : true;
};

/**
 * Administration, for administrators.
 *
 * Separate from `authGuard` because "signed in" and "allowed to manage other
 * people's accounts" are different questions, and conflating them is how a
 * viewer ends up on a page that lists every user in the institution.
 *
 * This is a convenience, not a control. The backend enforces the same rule, and
 * has to: a guard in the browser is a courtesy to the honest user and no
 * obstacle at all to anyone else.
 */
export const adminGuard: CanActivateFn = async (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  // Calls the shared helper, not `authGuard`.
  //
  // Invoking one CanActivateFn from another compiles only by accident: their
  // declared return type is Angular's `GuardResult`, which also admits
  // `RedirectCommand` and an `Observable`, so the value cannot be handed back
  // from a function promising `boolean | UrlTree`. Sharing a plain helper with
  // a precise `true | UrlTree` return is both what the compiler wants and the
  // clearer design — a guard is a decision, not a base class.
  const session = await requireSession(state.url);
  if (session !== true) return session;

  return auth.isAdmin() ? true : router.createUrlTree(['/lab']);
};
