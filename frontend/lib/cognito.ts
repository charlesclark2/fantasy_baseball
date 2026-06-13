import { CognitoUser, CognitoUserPool, AuthenticationDetails } from "amazon-cognito-identity-js"

const pool = new CognitoUserPool({
  UserPoolId: process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID!,
  ClientId: process.env.NEXT_PUBLIC_COGNITO_APP_CLIENT_ID!,
})

export function getCognitoUser(email: string) {
  return new CognitoUser({ Username: email, Pool: pool })
}

export { AuthenticationDetails }
