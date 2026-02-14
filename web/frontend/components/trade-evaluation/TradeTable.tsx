"use client";

import { useRecentTrades } from "@/hooks/useTradeEvaluation";
import { GradeCard } from "./GradeCard";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, XCircle } from "lucide-react";

interface TradeTableProps {
  limit?: number;
}

function formatDuration(minutes: number): string {
  if (minutes < 60) {
    return `${Math.round(minutes)}m`;
  }
  const hours = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const exitTypeBadgeColors: Record<string, string> = {
  TAKE_PROFIT: "bg-green-500/10 text-green-500 border-green-500/30",
  STOP_LOSS: "bg-orange-500/10 text-orange-500 border-orange-500/30",
  MANUAL: "bg-blue-500/10 text-blue-500 border-blue-500/30",
  REVERSAL: "bg-purple-500/10 text-purple-500 border-purple-500/30",
};

const exitTypeLabels: Record<string, string> = {
  TAKE_PROFIT: "止盈",
  STOP_LOSS: "止损",
  MANUAL: "手动",
  REVERSAL: "反转",
};

export function TradeTable({ limit = 20 }: TradeTableProps) {
  const { trades, isLoading, isError } = useRecentTrades(limit);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>最近交易评估</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">加载中...</div>
        </CardContent>
      </Card>
    );
  }

  if (isError || trades.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>最近交易评估</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">暂无交易数据</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>最近 {trades.length} 笔交易评估</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-24">时间</TableHead>
                <TableHead className="w-16">Grade</TableHead>
                <TableHead className="w-28">R/R (计划→实际)</TableHead>
                <TableHead className="w-20">出场</TableHead>
                <TableHead className="w-24">持仓时长</TableHead>
                <TableHead className="w-20 text-center">方向</TableHead>
                <TableHead className="w-20">信心</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {trades.map((trade, idx) => (
                <TableRow key={idx}>
                  <TableCell className="font-mono text-xs">
                    {formatTimestamp(trade.timestamp)}
                  </TableCell>
                  <TableCell>
                    <GradeCard grade={trade.grade} size="sm" />
                  </TableCell>
                  <TableCell className="font-mono text-sm">
                    <div className="flex items-center gap-1">
                      <span className="text-muted-foreground">
                        {trade.planned_rr.toFixed(1)}
                      </span>
                      <span className="text-muted-foreground">→</span>
                      <span className={trade.actual_rr >= 0 ? "text-green-500" : "text-red-500"}>
                        {trade.actual_rr.toFixed(1)}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={exitTypeBadgeColors[trade.exit_type] || ""}
                    >
                      {exitTypeLabels[trade.exit_type] || trade.exit_type}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-sm">
                    {formatDuration(trade.hold_duration_min)}
                  </TableCell>
                  <TableCell className="text-center">
                    {trade.direction_correct ? (
                      <CheckCircle2 className="h-4 w-4 text-green-500 inline" />
                    ) : (
                      <XCircle className="h-4 w-4 text-red-500 inline" />
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={trade.confidence === "HIGH" ? "default" : "outline"}>
                      {trade.confidence}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
