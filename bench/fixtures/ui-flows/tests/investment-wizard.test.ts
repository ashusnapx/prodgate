import assert from 'node:assert/strict';
import { test } from 'node:test';
import { FakeBackend } from '../src/api.ts';
import { InvestmentWizard } from '../src/flows/investment-wizard.ts';

function filled(wizard: InvestmentWizard) {
  wizard.set('company', 'Acme Robotics');
  assert.equal(wizard.next(), true);
  wizard.set('amount', '2500000');
  wizard.set('ownershipPct', '12.5');
  wizard.set('closeDate', '2026-03-31');
  assert.equal(wizard.next(), true);
}

test('walks the steps and submits', async () => {
  const api = new FakeBackend();
  const wizard = new InvestmentWizard(api);
  wizard.open('fund-1');
  filled(wizard);
  assert.equal(wizard.step.id, 'review');
  await wizard.submit();
  assert.equal(wizard.createdId, 'inv-1');
  assert.deepEqual(api.investments[0], {
    id: 'inv-1',
    fundId: 'fund-1',
    company: 'Acme Robotics',
    round: 'Series A',
    amount: 2_500_000,
    ownershipPct: 12.5,
    closeDate: '2026-03-31',
  });
});

test('next is blocked by invalid answers', () => {
  const wizard = new InvestmentWizard(new FakeBackend());
  wizard.open('fund-1');
  assert.equal(wizard.next(), false);
  assert.deepEqual(wizard.errors, { company: 'Enter the company name' });
  wizard.set('company', 'Acme');
  assert.deepEqual(wizard.errors, {});
  wizard.next();
  wizard.set('ownershipPct', '140');
  assert.equal(wizard.next(), false);
  assert.equal(wizard.errors.ownershipPct, 'Ownership must be between 0 and 100%');
});

test('stepper only opens steps already reached', () => {
  const wizard = new InvestmentWizard(new FakeBackend());
  wizard.open('fund-1');
  assert.equal(wizard.goTo(2), false);
  filled(wizard);
  assert.equal(wizard.goTo(0), true);
  assert.equal(wizard.step.id, 'company');
});

test('double click on submit creates one investment', async () => {
  const api = new FakeBackend();
  const wizard = new InvestmentWizard(api);
  wizard.open('fund-1');
  filled(wizard);
  await Promise.all([wizard.submit(), wizard.submit()]);
  assert.equal(api.investments.length, 1);
});

test('reopening the same fund keeps progress', () => {
  const wizard = new InvestmentWizard(new FakeBackend());
  wizard.open('fund-1');
  filled(wizard);
  wizard.open('fund-1');
  assert.equal(wizard.step.id, 'review');
});
