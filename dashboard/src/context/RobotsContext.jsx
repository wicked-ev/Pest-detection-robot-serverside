import React, { createContext, useState, useCallback } from 'react'

export const RobotsContext = createContext()

export function RobotsProvider({ children }) {
  const [robots, setRobots] = useState({})
  const [selectedRobotId, setSelectedRobotId] = useState(null)

  const updateRobots = useCallback((robotList) => {
    const robotMap = {}
    robotList.forEach((robot) => {
      robotMap[robot.robot_id] = robot
    })
    setRobots(robotMap)
  }, [])

  const selectRobot = useCallback((id) => {
    setSelectedRobotId(id)
  }, [])

  const value = {
    robots,
    selectedRobotId,
    updateRobots,
    selectRobot,
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
