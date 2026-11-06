import { NextResponse } from 'next/server'
import { currentUser } from '@/lib/auth/server'
export const dynamic='force-dynamic'
export async function GET(req:Request) {return NextResponse.json({user:await currentUser(req)},{headers:{'Cache-Control':'no-store'}})}
