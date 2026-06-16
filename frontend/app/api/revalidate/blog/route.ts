import { revalidatePath } from "next/cache"
import { NextResponse } from "next/server"

export async function POST() {
  revalidatePath("/blog")
  revalidatePath("/blog/[id]", "page")
  revalidatePath("/")
  return NextResponse.json({ revalidated: true })
}
