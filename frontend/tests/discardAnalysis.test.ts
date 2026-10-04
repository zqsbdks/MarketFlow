import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import DiscardAnalysis from '../src/components/DiscardAnalysis.vue'
test('selected breakdowns respect table and chart display modes', async () => {
  const groups = [{ title: '废弃原因占比', literal: false, items: [{ key: 'expired', name: '过期', quantity: 3, cost: '12.00', cost_share: '100.00' }] }]
  const wrapper = mount(DiscardAnalysis, { props: { groups, showTables: true, showCharts: false } })
  expect(wrapper.find('table').exists()).toBe(true)
  expect(wrapper.find('meter').exists()).toBe(false)
  await wrapper.setProps({ showTables: false, showCharts: true })
  expect(wrapper.find('table').exists()).toBe(false)
  expect(wrapper.find('meter').exists()).toBe(true)
  await wrapper.setProps({ groups: [] })
  expect(wrapper.find('.loss-groups').exists()).toBe(false)
  wrapper.unmount()
})
