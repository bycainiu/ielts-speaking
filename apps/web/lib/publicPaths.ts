const PUBLIC_EXACT_PATHS = new Set(["/", "/login", "/register", "/pricing"]);

export function isPublicPath(pathname: string): boolean {
  if (PUBLIC_EXACT_PATHS.has(pathname)) return true;
  if (pathname.startsWith("/pricing/")) return true;
  return false;
}

export function resolveHomeDestination(isAuthenticated: boolean): string {
  return isAuthenticated ? "/practice" : "/pricing";
}
