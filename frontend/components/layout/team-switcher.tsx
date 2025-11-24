"use client"

import * as React from "react"
import Image from "next/image"

import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"

export function TeamSwitcher() {
  const { state } = useSidebar()
  const isCollapsed = state === "collapsed"

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <div className={`flex items-center justify-center p-4 ${isCollapsed ? 'px-2' : ''}`}>
          {isCollapsed ? (
            <Image
              src="/ezscm-symbol.jpeg"
              alt="ezSCM"
              width={40}
              height={40}
              className="object-contain rounded-lg"
              priority
            />
          ) : (
            <Image
              src="/ezSCM-logo.svg"
              alt="ezSCM"
              width={160}
              height={50}
              className="object-contain"
              priority
            />
          )}
        </div>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}

