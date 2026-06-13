import { CognitoUser, CognitoUserPool, AuthenticationDetails } from "amazon-cognito-identity-js"

let _pool: CognitoUserPool | null = null

function getPool(): CognitoUserPool {
  if (!_pool) {
    _pool = new CognitoUserPool({
      UserPoolId: process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID!,
      ClientId: process.env.NEXT_PUBLIC_COGNITO_APP_CLIENT_ID!,
      Storage: typeof window !== "undefined" ? window.sessionStorage : undefined,
    })
  }
  return _pool
}

export function getCognitoUser(email: string) {
  return new CognitoUser({ Username: email, Pool: getPool() })
}

export function getCurrentCognitoUser() {
  return getPool().getCurrentUser()
}

export { AuthenticationDetails }
