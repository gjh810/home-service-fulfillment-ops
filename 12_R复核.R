# 第 12–14 天：只用 base R 复核城市指标，并绘制按创建周的异常率。
# 在仓库根目录运行：Rscript 12_R复核.R

orders <- read.csv(
  "03_模拟工单.csv", fileEncoding = "UTF-8-BOM",
  check.names = FALSE, stringsAsFactors = FALSE, colClasses = "character"
)
as_of <- "2026-09-30 23:59"
valid <- orders$appointment_deadline <= as_of & orders$completion_deadline <= as_of
orders <- orders[valid, ]

# 全部时间格式一致，均为北京时间 YYYY-MM-DD HH:MM；非空字符串可直接比较先后。
orders$on_time_visit <- !is.na(orders$arrived_at) & orders$arrived_at != "" &
  orders$arrived_at <= orders$appointment_deadline
orders$on_time_finish <- !is.na(orders$completed_at) & orders$completed_at != "" &
  orders$completed_at <= orders$completion_deadline
orders$complaint <- orders$complaint_flag == "1"
orders$exception <- orders$primary_exception != "无"
orders$closed <- orders$exception & !is.na(orders$exception_closed_at) &
  orders$exception_closed_at != ""

summarize_city <- function(x) {
  data.frame(
    city = x$city[1], orders = nrow(x),
    on_time_visit = sum(x$on_time_visit),
    visit_rate = round(mean(x$on_time_visit), 4),
    on_time_finish = sum(x$on_time_finish),
    finish_rate = round(mean(x$on_time_finish), 4),
    complaints = sum(x$complaint),
    exceptions = sum(x$exception),
    closed = sum(x$closed)
  )
}
city_summary <- do.call(rbind, lapply(split(orders, orders$city), summarize_city))
rownames(city_summary) <- NULL
write.csv(city_summary, "12_R城市复核.csv", row.names = FALSE, fileEncoding = "UTF-8")

# 按工单创建周计算异常率。首末周可能不足 7 天，因此显示分母。
created <- as.Date(substr(orders$created_at, 1, 10))
week_start <- created - ((as.POSIXlt(created)$wday + 6) %% 7)
weeks <- sort(unique(week_start))
week_orders <- vapply(weeks, function(w) sum(week_start == w), integer(1))
week_exceptions <- vapply(weeks, function(w) sum(orders$exception[week_start == w]), integer(1))
week_rate <- week_exceptions / week_orders

dir.create("assets", showWarnings = FALSE)
png("assets/12_R每周异常率.png", width = 1200, height = 650, res = 135)
par(mar = c(5, 5, 4, 2), family = "sans", bg = "white")
plot(
  seq_along(weeks), week_rate * 100, type = "b", pch = 19, lwd = 2.5,
  col = "#176B67", ylim = c(0, max(week_rate * 100) + 12),
  xlim = c(0.2, length(weeks) + 0.8), xaxt = "n",
  xlab = "Week starting (Beijing time)", ylab = "Primary exception rate (%)",
  main = "Synthetic orders: exception rate by creation week"
)
axis(1, at = seq_along(weeks), labels = format(weeks, "%m-%d"))
grid(nx = NA, ny = NULL, col = "#DDE4E8", lty = 1)
lines(seq_along(weeks), week_rate * 100, type = "b", pch = 19, lwd = 2.5, col = "#176B67")
text(seq_along(weeks), week_rate * 100 + 4,
     labels = paste0(round(week_rate * 100, 1), "%  n=", week_orders), cex = 0.85)
dev.off()

cat("rows=", nrow(orders), " visit=", sum(orders$on_time_visit),
    " finish=", sum(orders$on_time_finish), " complaints=", sum(orders$complaint),
    " exceptions=", sum(orders$exception), " closed=", sum(orders$closed), "\n", sep = "")
print(city_summary)
