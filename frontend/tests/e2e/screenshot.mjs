// Capture screenshots of the live app: home, a bot chat with a real reply.
import { chromium } from '@playwright/test'

const URL = process.env.BASE_URL || 'http://localhost:8080'
const OUT = process.env.OUT || '/tmp'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 820 } })
const uid = 'shot-' + Date.now().toString(36)
await page.addInitScript((u) => localStorage.setItem('cs-agent-studio-uid', u), uid)

await page.goto(URL, { waitUntil: 'networkidle' })
await page.waitForTimeout(800)
await page.screenshot({ path: `${OUT}/live-home.png` })

// Create a bot
await page.getByRole('button', { name: 'Tạo bot mới', exact: true }).click()
const dialog = page.getByRole('dialog')
await dialog.getByLabel('Tên bot').fill('ZingSpeed Mobile')
await dialog.getByLabel('Cách gọi người chơi').fill('tay đua')
await dialog.getByLabel('Cách bot tự xưng').fill('mình')
await dialog.getByRole('button', { name: 'Tạo bot', exact: true }).click()
await page.waitForTimeout(1500)
await page.screenshot({ path: `${OUT}/live-bot.png` })

// Chat: greeting + on-topic
const input = page.locator('.composer textarea')
await input.fill('alo shop ơi')
await input.press('Enter')
await page.waitForTimeout(3000)
await input.fill('mình quên mật khẩu thì làm sao')
await input.press('Enter')
await page.waitForTimeout(13000)
await page.screenshot({ path: `${OUT}/live-chat.png`, fullPage: false })

await browser.close()
console.log('screenshots saved to', OUT)
