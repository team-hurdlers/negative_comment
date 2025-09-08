"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Bell, Play, Square, Activity, AlertCircle, CheckCircle2, ExternalLink } from "lucide-react"

interface ProductInfo {
  title: string
  price: string
  url: string
}

interface MonitorResult {
  timestamp: string
  change: string
  type: "positive" | "negative" | "neutral"
}

export default function ProductMonitor() {
  const [url, setUrl] = useState("")
  const [interval, setInterval] = useState(30)
  const [productInfo, setProductInfo] = useState<ProductInfo | null>(null)
  const [isMonitoring, setIsMonitoring] = useState(false)
  const [results, setResults] = useState<MonitorResult[]>([])
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission>("default")

  useEffect(() => {
    if ("Notification" in window) {
      setNotificationPermission(Notification.permission)
    }
  }, [])

  const requestNotificationPermission = async () => {
    if ("Notification" in window) {
      const permission = await Notification.requestPermission()
      setNotificationPermission(permission)
    }
  }

  const startMonitoring = () => {
    setIsMonitoring(true)
    // Simulate product info fetch
    setProductInfo({
      title: "Sample Product Name",
      price: "$299.99",
      url: url,
    })
  }

  const stopMonitoring = () => {
    setIsMonitoring(false)
  }

  const analyzeChanges = () => {
    // Simulate analysis results
    const mockResults: MonitorResult[] = [
      {
        timestamp: new Date().toLocaleString(),
        change: "Price decreased by $20.00",
        type: "positive",
      },
      {
        timestamp: new Date(Date.now() - 3600000).toLocaleString(),
        change: "Product went out of stock",
        type: "negative",
      },
      {
        timestamp: new Date(Date.now() - 7200000).toLocaleString(),
        change: "No significant changes detected",
        type: "neutral",
      },
    ]
    setResults(mockResults)
  }

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-4xl space-y-8">
        {/* Header */}
        <div className="text-center space-y-4">
          <h1 className="text-4xl font-bold text-foreground tracking-tight">Product Monitor</h1>
          <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
            Track product changes and get notified when prices drop or availability changes
          </p>
        </div>

        {/* Main Content */}
        <Tabs defaultValue="monitor" className="space-y-6">
          <TabsList className="grid w-full grid-cols-2 bg-muted">
            <TabsTrigger value="monitor" className="data-[state=active]:bg-background">
              <Activity className="w-4 h-4 mr-2" />
              Monitor
            </TabsTrigger>
            <TabsTrigger value="notifications" className="data-[state=active]:bg-background">
              <Bell className="w-4 h-4 mr-2" />
              Notifications
            </TabsTrigger>
          </TabsList>

          <TabsContent value="monitor" className="space-y-6">
            {/* URL Input Section */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ExternalLink className="w-5 h-5" />
                  Product URL
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Input
                  type="url"
                  placeholder="Enter product URL to monitor"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  className="text-base"
                />
                <p className="text-sm text-muted-foreground">
                  Supported sites: Amazon, eBay, Best Buy, Target, and more
                </p>

                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-2">
                    <label htmlFor="interval" className="text-sm font-medium">
                      Check interval:
                    </label>
                    <Input
                      id="interval"
                      type="number"
                      min="5"
                      max="1440"
                      value={interval}
                      onChange={(e) => setInterval(Number(e.target.value))}
                      className="w-20"
                    />
                    <span className="text-sm text-muted-foreground">minutes</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Product Info */}
            {productInfo && (
              <Card className="border-l-4 border-l-accent">
                <CardContent className="pt-6">
                  <div className="space-y-2">
                    <h3 className="text-xl font-semibold text-foreground">{productInfo.title}</h3>
                    <p className="text-2xl font-bold text-accent">{productInfo.price}</p>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Monitor Controls */}
            <Card>
              <CardContent className="pt-6">
                <div className="flex flex-wrap gap-3">
                  <Button
                    onClick={startMonitoring}
                    disabled={!url || isMonitoring}
                    className="bg-primary hover:bg-primary/90"
                  >
                    <Play className="w-4 h-4 mr-2" />
                    Start Monitoring
                  </Button>

                  <Button onClick={stopMonitoring} disabled={!isMonitoring} variant="destructive">
                    <Square className="w-4 h-4 mr-2" />
                    Stop Monitoring
                  </Button>

                  <Button
                    onClick={analyzeChanges}
                    variant="outline"
                    className="border-accent text-accent hover:bg-accent hover:text-accent-foreground bg-transparent"
                  >
                    <Activity className="w-4 h-4 mr-2" />
                    Analyze Changes
                  </Button>
                </div>

                {/* Status Display */}
                {isMonitoring && (
                  <div className="mt-4 p-4 bg-muted rounded-lg border-l-4 border-l-accent">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 bg-accent rounded-full animate-pulse" />
                      <span className="text-sm font-medium">Monitoring active - Checking every {interval} minutes</span>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Results */}
            {results.length > 0 && (
              <div className="space-y-4">
                <h2 className="text-2xl font-semibold text-foreground">Analysis Results</h2>
                <div className="space-y-3">
                  {results.map((result, index) => (
                    <Card
                      key={index}
                      className={`border-l-4 ${
                        result.type === "positive"
                          ? "border-l-accent bg-accent/5"
                          : result.type === "negative"
                            ? "border-l-destructive bg-destructive/5"
                            : "border-l-muted-foreground bg-muted/50"
                      }`}
                    >
                      <CardContent className="pt-4">
                        <div className="flex items-start justify-between">
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              {result.type === "positive" ? (
                                <CheckCircle2 className="w-4 h-4 text-accent" />
                              ) : result.type === "negative" ? (
                                <AlertCircle className="w-4 h-4 text-destructive" />
                              ) : (
                                <Activity className="w-4 h-4 text-muted-foreground" />
                              )}
                              <span className="font-medium text-foreground">{result.change}</span>
                            </div>
                            <p className="text-sm text-muted-foreground">{result.timestamp}</p>
                          </div>
                          <Badge
                            variant={
                              result.type === "positive"
                                ? "default"
                                : result.type === "negative"
                                  ? "destructive"
                                  : "secondary"
                            }
                          >
                            {result.type}
                          </Badge>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value="notifications" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Bell className="w-5 h-5" />
                  Notification Settings
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-muted rounded-lg">
                  <div className="space-y-1">
                    <p className="font-medium text-foreground">Browser Notifications</p>
                    <p className="text-sm text-muted-foreground">Get notified when product changes are detected</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={
                        notificationPermission === "granted"
                          ? "default"
                          : notificationPermission === "denied"
                            ? "destructive"
                            : "secondary"
                      }
                    >
                      {notificationPermission === "granted"
                        ? "Enabled"
                        : notificationPermission === "denied"
                          ? "Blocked"
                          : "Not Set"}
                    </Badge>
                    {notificationPermission !== "granted" && (
                      <Button
                        onClick={requestNotificationPermission}
                        size="sm"
                        className="bg-accent hover:bg-accent/90"
                      >
                        Enable
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
