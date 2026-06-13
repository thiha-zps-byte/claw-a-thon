import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

// End-to-end smoke against a running app (local build or the live prod endpoint).
// Flow: load → create bot → chat → reply appears. Plus an axe a11y scan.

test('create a bot and chat with it', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('CS Agent Studio')).toBeVisible()

  // Open the create-bot dialog (icon button has an aria-label).
  await page.getByRole('button', { name: 'Tạo bot mới', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Tên bot').fill('ZingSpeed E2E')
  await dialog.getByLabel('Cách gọi người chơi').fill('tay đua')
  await dialog.getByRole('button', { name: 'Tạo bot', exact: true }).click()

  // Workspace opens on the new bot; the address line shows the xưng hô.
  await expect(page.getByText(/tay đua/)).toBeVisible({ timeout: 20_000 })

  // Send a greeting (fast path) and expect a reply bubble.
  const input = page.locator('.composer textarea')
  await input.fill('alo shop ơi')
  await input.press('Enter')
  await expect(page.locator('.row.bot .bubble').last()).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('.row.bot .bubble').last()).toContainText(/tay đua|mình/)
})

test('no critical accessibility violations on the home screen', async ({ page }) => {
  await page.goto('/')
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze()
  const critical = results.violations.filter((v) => v.impact === 'critical')
  expect(critical, JSON.stringify(critical.map((c) => c.id))).toHaveLength(0)
})
