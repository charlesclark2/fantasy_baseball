"use client"

import { createContext, useContext, useState } from "react"
import { format } from "date-fns"

type DateCtx = {
  selectedDate: Date
  setSelectedDate: (d: Date) => void
  isoDate: string
  isToday: boolean
}

export const DateContext = createContext<DateCtx>({
  selectedDate: new Date(),
  setSelectedDate: () => {},
  isoDate: format(new Date(), "yyyy-MM-dd"),
  isToday: true,
})

export function DateProvider({ children }: { children: React.ReactNode }) {
  const [selectedDate, setSelectedDate] = useState<Date>(new Date())
  const isoDate = format(selectedDate, "yyyy-MM-dd")
  const isToday = isoDate === format(new Date(), "yyyy-MM-dd")
  return (
    <DateContext.Provider value={{ selectedDate, setSelectedDate, isoDate, isToday }}>
      {children}
    </DateContext.Provider>
  )
}

export function useSelectedDate() {
  return useContext(DateContext)
}
