import React, { createContext, useState, useCallback } from 'react'

export const RobotsContext = createContext()

export function RobotsProvider({ children }) {
  const [robots, setRobots] = useState({})
  const [selectedRobotId, setSelectedRobotId] = useState(null)
  const [refreshRobots, setRefreshRobots] = useState(null)
  const [robotsError, setRobotsError] = useState(null)
  // Which page is shown: 'live' (one robot's stream) or 'history' (all sightings).
  const [view, setView] = useState('live')
  // Robot filter for the history page ('' means all robots).
  const [historyRobotId, setHistoryRobotId] = useState('')

  const updateRobots = useCallback((robotList) => {
    const robotMap = {}
    robotList.forEach((robot) => {
      robotMap[robot.robot_id] = robot
    })
    setRobots(robotMap)
  }, [])

  const selectRobot = useCallback((id) => {
    setSelectedRobotId(id)
    setView('live')
  }, [])

  const openHistory = useCallback((robotId = '') => {
    setHistoryRobotId(robotId)
    setView('history')
  }, [])

  const registerRefreshRobots = useCallback((refreshFn) => {
    setRefreshRobots(() => refreshFn)
  }, [])

  const value = {
    robots,
    selectedRobotId,
    updateRobots,
    selectRobot,
    refreshRobots,
    registerRefreshRobots,
    robotsError,
    setRobotsError,
    view,
    setView,
    historyRobotId,
    setHistoryRobotId,
    openHistory,
  }

  return <RobotsContext.Provider value={value}>{children}</RobotsContext.Provider>
}

export function useRobotsContext() {
  const context = React.useContext(RobotsContext)
  if (!context) {
    throw new Error('useRobotsContext must be used within RobotsProvider')
  }
  return context
}
